from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import Database
from app.sync import RunTotals, SyncEngine


class RetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = Database(root / "data" / "archive.sqlite3")
        self.engine = SyncEngine(self.db, root / "archive")

    def _add_item(
        self,
        filename: str,
        *,
        category: str = "recordings",
        age_days: int = 1,
        size: int = 10,
        sidecars: bool = False,
    ) -> dict:
        recorded = datetime.now(timezone.utc) - timedelta(days=age_days)
        relative = Path("vehicles") / "car" / category / filename
        path = self.engine.archive_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = filename.encode("utf-8")[:1] * size
        path.write_bytes(raw)
        if sidecars and category == "recordings":
            path.with_suffix(".jpg").write_bytes(b"jpg")
            path.with_suffix(".metadata.json").write_bytes(b"{}")
            path.with_suffix(".events.json").write_bytes(b"{}")
            partial = path.with_suffix(path.suffix + ".part")
            partial.write_bytes(b"partial")
            partial.with_name(partial.name + ".meta").write_bytes(b"{}")
        source_key = f"source:{category}:{filename}"
        self.assertTrue(
            self.db.add_item(
                source_key=source_key,
                category=category,
                subtype="drive" if category == "recordings" else "",
                vehicle="car",
                filename=filename,
                relative_path=str(relative),
                media_type="video/mp4" if category == "recordings" else "application/json",
                size_bytes=size,
                sha256=hashlib.sha256(raw).hexdigest(),
                source_timestamp=int(recorded.timestamp() * 1000),
                metadata={},
            )
        )
        return self.db.get_item_by_source_key(source_key)

    def _save_recording_policy(
        self,
        *,
        age_days: int = 30,
        keep_latest: int | None = None,
        storage_limit: int | None = None,
    ) -> dict:
        return self.db.save_settings(
            {
                "retention": {
                    "categories": {
                        "recordings": {
                            "enabled": True,
                            "value": age_days,
                            "unit": "days",
                            "keep_latest_enabled": keep_latest is not None,
                            "keep_latest_count": keep_latest or 1,
                        }
                    },
                    "storage_limit": {
                        "enabled": storage_limit is not None,
                        "max_bytes": storage_limit or 0,
                    },
                }
            }
        )

    def test_age_retention_deletes_only_local_old_copy_and_sidecars(self) -> None:
        oldest = self._add_item("oldest.mp4", age_days=180, sidecars=True)
        newest = self._add_item("newest.mp4", age_days=150, sidecars=True)
        settings = self._save_recording_policy(age_days=30, keep_latest=1)

        result = self.engine.apply_retention(settings)

        self.assertEqual(result["deleted_items"], 1)
        self.assertFalse(
            (self.engine.archive_root / oldest["relative_path"]).exists()
        )
        self.assertFalse(
            (self.engine.archive_root / oldest["relative_path"]).with_suffix(".jpg").exists()
        )
        oldest_partial = (self.engine.archive_root / oldest["relative_path"]).with_suffix(
            ".mp4.part"
        )
        self.assertFalse(oldest_partial.exists())
        self.assertFalse(oldest_partial.with_name(oldest_partial.name + ".meta").exists())
        self.assertTrue(
            (self.engine.archive_root / newest["relative_path"]).exists()
        )
        self.assertTrue(self.db.is_retention_tombstoned(oldest["source_key"]))
        self.assertFalse(self.db.is_retention_tombstoned(newest["source_key"]))

    def test_primary_staging_failure_preserves_sidecars_and_inventory(self) -> None:
        item = self._add_item("blocked.mp4", age_days=180, sidecars=True)
        primary = self.engine.archive_root / item["relative_path"]
        thumbnail = primary.with_suffix(".jpg")
        settings = self._save_recording_policy(age_days=1)
        original_replace = Path.replace

        def guarded_replace(path: Path, *args, **kwargs):
            if path == primary:
                raise PermissionError("blocked for test")
            return original_replace(path, *args, **kwargs)

        with patch.object(Path, "replace", guarded_replace):
            result = self.engine.apply_retention(settings)

        self.assertEqual(result["deleted_items"], 0)
        self.assertEqual(result["error_count"], 1)
        self.assertTrue(primary.exists())
        self.assertTrue(thumbnail.exists())
        self.assertIsNotNone(self.db.get_item(int(item["id"])))
        self.assertFalse(self.db.is_retention_tombstoned(item["source_key"]))

    def test_database_false_restores_staged_primary_without_a_tombstone(self) -> None:
        item = self._add_item("db-false.mp4", age_days=180, sidecars=True)
        primary = self.engine.archive_root / item["relative_path"]
        thumbnail = primary.with_suffix(".jpg")
        settings = self._save_recording_policy(age_days=1)

        with patch.object(self.db, "delete_archive_item", return_value=False):
            result = self.engine.apply_retention(settings)

        self.assertEqual(result["deleted_items"], 0)
        self.assertEqual(result["error_count"], 1)
        self.assertTrue(primary.exists())
        self.assertTrue(thumbnail.exists())
        self.assertEqual(list(primary.parent.glob(".retention-*.pending")), [])
        self.assertIsNotNone(self.db.get_item(int(item["id"])))
        self.assertFalse(self.db.is_retention_tombstoned(item["source_key"]))

    def test_database_exception_restores_staged_primary_without_a_tombstone(self) -> None:
        item = self._add_item("db-error.mp4", age_days=180, sidecars=True)
        primary = self.engine.archive_root / item["relative_path"]
        settings = self._save_recording_policy(age_days=1)

        with patch.object(
            self.db,
            "delete_archive_item",
            side_effect=RuntimeError("database unavailable for test"),
        ):
            result = self.engine.apply_retention(settings)

        self.assertEqual(result["deleted_items"], 0)
        self.assertEqual(result["error_count"], 1)
        self.assertTrue(primary.exists())
        self.assertEqual(list(primary.parent.glob(".retention-*.pending")), [])
        self.assertIsNotNone(self.db.get_item(int(item["id"])))
        self.assertFalse(self.db.is_retention_tombstoned(item["source_key"]))

    def test_sidecar_delete_failure_still_exposes_deleted_local_placeholder(self) -> None:
        item = self._add_item("sidecar-blocked.mp4", age_days=180, sidecars=True)
        primary = self.engine.archive_root / item["relative_path"]
        thumbnail = primary.with_suffix(".jpg")
        settings = self._save_recording_policy(age_days=1)
        original_unlink = Path.unlink

        def guarded_unlink(path: Path, *args, **kwargs):
            if path == thumbnail:
                raise PermissionError("blocked sidecar for test")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", guarded_unlink):
            result = self.engine.apply_retention(settings)

        self.assertEqual(result["deleted_items"], 1)
        self.assertEqual(result["error_count"], 1)
        self.assertFalse(primary.exists())
        self.assertTrue(thumbnail.exists())
        self.assertIsNone(self.db.get_item(int(item["id"])))
        self.assertTrue(self.db.is_retention_tombstoned(item["source_key"]))

    def test_storage_limit_deletes_oldest_unprotected_items_by_actual_bytes(self) -> None:
        oldest = self._add_item("oldest.mp4", age_days=3, size=10)
        middle = self._add_item("middle.mp4", age_days=2, size=10)
        newest = self._add_item("newest.mp4", age_days=1, size=10)
        settings = self._save_recording_policy(
            age_days=10_000,
            keep_latest=1,
            storage_limit=15,
        )

        result = self.engine.apply_retention(settings)

        self.assertTrue(result["limit_satisfied"])
        self.assertEqual(result["deleted_items"], 2)
        self.assertTrue(self.db.is_retention_tombstoned(oldest["source_key"]))
        self.assertTrue(self.db.is_retention_tombstoned(middle["source_key"]))
        self.assertFalse(self.db.is_retention_tombstoned(newest["source_key"]))
        self.assertEqual(len(self.db.list_items(category="recordings")), 1)

    def test_protected_latest_item_is_not_deleted_to_force_the_quota(self) -> None:
        only = self._add_item("only.mp4", age_days=180, size=20)
        settings = self._save_recording_policy(
            age_days=1,
            keep_latest=1,
            storage_limit=10,
        )

        result = self.engine.apply_retention(settings)

        self.assertEqual(result["deleted_items"], 0)
        self.assertFalse(result["limit_satisfied"])
        self.assertTrue((self.engine.archive_root / only["relative_path"]).exists())
        self.assertIsNotNone(self.db.get_item_by_source_key(only["source_key"]))

    def test_retained_recording_is_not_downloaded_again_from_the_vehicle(self) -> None:
        settings = self.db.save_settings(
            {
                "vehicle": {
                    "name": "Car",
                    "base_url": "https://vehicle.example",
                    "device_token": "test",
                    "device_id": "vehicle-id",
                },
                "schedule": {"only_wifi": False},
                "content": {
                    "categories": ["recordings"],
                    "recording_types": ["normal"],
                    "include_unknown_recording_types": False,
                    "include_thumbnails": False,
                    "include_event_timeline": False,
                },
            }
        )
        timestamp = int((datetime.now(timezone.utc) - timedelta(days=180)).timestamp() * 1000)

        class Client:
            def __init__(self):
                self.downloads = 0

            def iter_recordings(self, *_args):
                yield {
                    "filename": "cam_old.mp4",
                    "type": "normal",
                    "timestamp": timestamp,
                    "size": 4,
                    "videoUrl": "/video/cam_old.mp4",
                }

            def status(self):
                return {"network": {"type": "wifi"}}

            def download_to(self, path, destination, **kwargs):
                self.downloads += 1
                destination.write_bytes(b"data")
                return 4, hashlib.sha256(b"data").hexdigest()

            @staticmethod
            def encoded_filename(filename):
                return filename

        client = Client()
        self.engine._collect_recordings(client, settings, RunTotals())
        self.assertEqual(client.downloads, 1)
        listed = self.db.list_items(category="recordings")[0]
        archived = self.db.get_item(listed["id"])
        self.assertIsNotNone(archived)

        retention = self._save_recording_policy(age_days=1)
        self.engine.apply_retention(retention)
        self.assertTrue(self.db.is_retention_tombstoned(archived["source_key"]))

        disabled = self.db.save_settings(
            {"retention": {"categories": {"recordings": {"enabled": False}}}}
        )
        self.engine._collect_recordings(client, disabled, RunTotals())
        self.assertEqual(client.downloads, 1)
        self.assertFalse(self.db.list_items(category="recordings"))

    def test_recording_age_policy_downloads_only_the_protected_latest_old_item(self) -> None:
        settings = self.db.save_settings(
            {
                "vehicle": {
                    "name": "Car",
                    "base_url": "https://vehicle.example",
                    "device_token": "test",
                    "device_id": "vehicle-id",
                },
                "schedule": {"only_wifi": False},
                "content": {
                    "categories": ["recordings"],
                    "recording_types": ["normal"],
                    "include_unknown_recording_types": False,
                    "include_thumbnails": False,
                    "include_event_timeline": False,
                },
                "retention": {
                    "categories": {
                        "recordings": {
                            "enabled": True,
                            "value": 1,
                            "unit": "days",
                            "keep_latest_enabled": True,
                            "keep_latest_count": 1,
                        }
                    }
                },
            }
        )
        now = datetime.now(timezone.utc)
        items = [
            {
                "filename": "cam_older.mp4",
                "type": "normal",
                "timestamp": int((now - timedelta(days=180)).timestamp() * 1000),
                "size": 4,
                "videoUrl": "/video/cam_older.mp4",
            },
            {
                "filename": "cam_latest.mp4",
                "type": "normal",
                "timestamp": int((now - timedelta(days=150)).timestamp() * 1000),
                "size": 4,
                "videoUrl": "/video/cam_latest.mp4",
            },
        ]

        class Client:
            def __init__(self):
                self.downloaded = []

            def iter_recordings(self, *_args):
                yield from items

            def status(self):
                return {"network": {"type": "wifi"}}

            def download_to(self, path, destination, **kwargs):
                self.downloaded.append(Path(path).name)
                destination.write_bytes(b"data")
                return 4, hashlib.sha256(b"data").hexdigest()

            @staticmethod
            def encoded_filename(filename):
                return filename

        client = Client()
        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloaded, ["cam_latest.mp4"])
        archived = self.db.list_items(category="recordings")
        self.assertEqual([item["filename"] for item in archived], ["cam_latest.mp4"])


if __name__ == "__main__":
    unittest.main()
