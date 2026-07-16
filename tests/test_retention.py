from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import Database, RetentionCleanupPending
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
        source_key: str | None = None,
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
        source_key = source_key or f"source:{category}:{filename}"
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

    def test_startup_restores_a_primary_staged_before_database_commit(self) -> None:
        item = self._add_item("crash-before-commit.mp4", age_days=180, sidecars=True)
        item_id = int(item["id"])
        primary = self.engine.archive_root / item["relative_path"]
        staged = primary.with_name(
            f".retention-{item_id}-{'a' * 24}.pending"
        )
        staged_relative = staged.relative_to(self.engine.archive_root)
        self.assertIsNotNone(
            self.db.prepare_retention_deletion(item_id, str(staged_relative))
        )
        primary.replace(staged)

        SyncEngine(self.db, self.engine.archive_root)

        self.assertTrue(primary.exists())
        self.assertFalse(staged.exists())
        self.assertIsNotNone(self.db.get_item(item_id))
        self.assertFalse(self.db.is_retention_tombstoned(item["source_key"]))
        self.assertEqual(self.db.list_retention_deletion_jobs(), [])

    def test_startup_finishes_cleanup_staged_after_database_commit(self) -> None:
        item = self._add_item("crash-after-commit.mp4", age_days=180, sidecars=True)
        item_id = int(item["id"])
        primary = self.engine.archive_root / item["relative_path"]
        thumbnail = primary.with_suffix(".jpg")
        staged = primary.with_name(
            f".retention-{item_id}-{'b' * 24}.pending"
        )
        staged_relative = staged.relative_to(self.engine.archive_root)
        self.assertIsNotNone(
            self.db.prepare_retention_deletion(item_id, str(staged_relative))
        )
        primary.replace(staged)
        self.assertTrue(self.db.delete_archive_item(item_id))

        SyncEngine(self.db, self.engine.archive_root)

        self.assertFalse(primary.exists())
        self.assertFalse(staged.exists())
        self.assertFalse(thumbnail.exists())
        self.assertIsNone(self.db.get_item(item_id))
        self.assertTrue(self.db.is_retention_tombstoned(item["source_key"]))
        self.assertEqual(self.db.list_retention_deletion_jobs(), [])

    def test_retention_preserves_path_referenced_by_legacy_duplicate_row(
        self,
    ) -> None:
        item = self._add_item("legacy-shared.mp4", age_days=180, sidecars=True)
        primary = self.engine.archive_root / item["relative_path"]
        other_source = "source:recordings:legacy-shared-alias"
        self.assertTrue(
            self.db.add_item(
                source_key=other_source,
                category="recordings",
                subtype="drive",
                vehicle="car",
                filename=item["filename"],
                relative_path=item["relative_path"],
                media_type="video/mp4",
                size_bytes=item["size_bytes"],
                sha256=item["sha256"],
                source_timestamp=item["source_timestamp"],
                metadata={},
            )
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO archive_retention_protections(
                    source_key,category,protected_at
                ) VALUES(?,?,?)
                """,
                (other_source, "recordings", datetime.now(timezone.utc).isoformat()),
            )

        result = self.engine.apply_retention(
            self._save_recording_policy(age_days=1)
        )

        self.assertEqual(result["deleted_items"], 1)
        self.assertEqual(result["deleted_bytes"], 0)
        self.assertTrue(primary.exists())
        self.assertTrue(primary.with_suffix(".jpg").exists())
        self.assertTrue(primary.with_suffix(".metadata.json").exists())
        self.assertTrue(self.db.is_retention_tombstoned(item["source_key"]))
        self.assertIsNotNone(self.db.get_item_by_source_key(other_source))

    def test_recovery_restores_staged_path_needed_by_legacy_duplicate_row(
        self,
    ) -> None:
        item = self._add_item("crash-shared.mp4", age_days=180, sidecars=True)
        item_id = int(item["id"])
        primary = self.engine.archive_root / item["relative_path"]
        other_source = "source:recordings:crash-shared-alias"
        self.assertTrue(
            self.db.add_item(
                source_key=other_source,
                category="recordings",
                subtype="drive",
                vehicle="car",
                filename=item["filename"],
                relative_path=item["relative_path"],
                media_type="video/mp4",
                size_bytes=item["size_bytes"],
                sha256=item["sha256"],
                source_timestamp=item["source_timestamp"],
                metadata={},
            )
        )
        staged = primary.with_name(
            f".retention-{item_id}-{'c' * 24}.pending"
        )
        self.assertIsNotNone(
            self.db.prepare_retention_deletion(
                item_id,
                str(staged.relative_to(self.engine.archive_root)),
            )
        )
        primary.replace(staged)
        self.assertTrue(self.db.delete_archive_item(item_id))

        SyncEngine(self.db, self.engine.archive_root)

        self.assertTrue(primary.exists())
        self.assertFalse(staged.exists())
        self.assertTrue(primary.with_suffix(".jpg").exists())
        self.assertIsNotNone(self.db.get_item_by_source_key(other_source))
        self.assertEqual(self.db.list_retention_deletion_jobs(), [])

    def test_graceful_stop_waits_for_active_retention_boundary(self) -> None:
        self.engine._retention_lock.acquire()
        entered = threading.Event()

        def stop_engine() -> None:
            entered.set()
            self.engine.stop()

        worker = threading.Thread(target=stop_engine)
        worker.start()
        self.assertTrue(entered.wait(1))
        self.assertTrue(worker.is_alive())

        self.engine._retention_lock.release()
        worker.join(1)

        self.assertFalse(worker.is_alive())
        self.assertEqual(
            self.engine.apply_retention()["status"],
            "deferred",
        )

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
        self.assertEqual(len(self.db.list_retention_deletion_jobs()), 1)

        SyncEngine(self.db, self.engine.archive_root)

        self.assertFalse(thumbnail.exists())
        self.assertEqual(self.db.list_retention_deletion_jobs(), [])

    def test_remote_disappearance_waits_for_sidecar_cleanup_journal(self) -> None:
        identity = "vehicle-one"
        source_key = (
            f"{identity}:recording:sidecar-remote-gone.mp4:1784196610000"
        )
        item = self._add_item(
            "sidecar-remote-gone.mp4",
            age_days=180,
            sidecars=True,
            source_key=source_key,
        )
        primary = self.engine.archive_root / item["relative_path"]
        thumbnail = primary.with_suffix(".jpg")
        original_unlink = Path.unlink

        def guarded_unlink(path: Path, *args, **kwargs):
            if path == thumbnail:
                raise PermissionError("blocked sidecar for test")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", guarded_unlink):
            result = self.engine.apply_retention(
                self._save_recording_policy(age_days=1)
            )

        self.assertEqual(result["deleted_items"], 1)
        self.assertEqual(result["error_count"], 1)
        self.assertTrue(self.db.is_retention_tombstoned(source_key))
        self.assertEqual(len(self.db.list_retention_deletion_jobs()), 1)

        reconciliation = self.db.reconcile_recording_tombstones(identity, {})

        self.assertEqual(reconciliation, {"updated": 0, "purged": 0})
        self.assertTrue(self.db.is_retention_tombstoned(source_key))
        self.assertEqual(len(self.db.list_retention_deletion_jobs()), 1)
        self.assertTrue(
            self.db.list_deleted_recordings(search="sidecar-remote")[0][
                "cleanup_pending"
            ]
        )
        with self.assertRaises(RetentionCleanupPending):
            self.db.request_recording_restore(source_key)

        self.assertEqual(self.engine._recover_retention_deletions(), 0)
        self.assertFalse(thumbnail.exists())
        self.assertEqual(self.db.list_retention_deletion_jobs(), [])
        self.assertTrue(self.db.is_retention_tombstoned(source_key))
        self.assertFalse(
            self.db.list_deleted_recordings(search="sidecar-remote")[0][
                "cleanup_pending"
            ]
        )

        reconciliation = self.db.reconcile_recording_tombstones(identity, {})

        self.assertEqual(reconciliation, {"updated": 0, "purged": 1})
        self.assertFalse(self.db.is_retention_tombstoned(source_key))

    def test_pending_restored_inventory_is_not_deleted_before_finalization(
        self,
    ) -> None:
        source_key = (
            "vehicle-one:recording:pending-restored.mp4:1784196610000"
        )
        original = self._add_item(
            "pending-restored.mp4",
            age_days=180,
            source_key=source_key,
        )
        primary = self.engine.archive_root / original["relative_path"]
        self.assertTrue(self.db.delete_archive_item(int(original["id"])))
        self.assertEqual(
            self.db.request_recording_restore(source_key),
            "vehicle-one",
        )
        self.assertTrue(
            self.db.add_item(
                source_key=source_key,
                category="recordings",
                subtype="drive",
                vehicle=str(original["vehicle"]),
                filename=str(original["filename"]),
                relative_path=str(original["relative_path"]),
                media_type=str(original["media_type"]),
                size_bytes=int(original["size_bytes"]),
                sha256=str(original["sha256"]),
                source_timestamp=int(original["source_timestamp"]),
                metadata={"restored": True},
            )
        )

        result = self.engine.apply_retention(
            self._save_recording_policy(age_days=1)
        )

        self.assertEqual(result["deleted_items"], 0)
        self.assertTrue(primary.is_file())
        self.assertTrue(self.db.recording_restore_requested(source_key))
        self.assertFalse(self.db.is_retention_protected(source_key))
        self.assertIsNotNone(self.db.get_item_by_source_key(source_key))

        self.assertTrue(self.db.complete_recording_restore(source_key))
        self.assertTrue(self.db.is_retention_protected(source_key))

    def test_cross_vehicle_partial_reference_blocks_cleanup_and_retention(
        self,
    ) -> None:
        source_key = "vehicle-one:recording:cross-vehicle.mp4:1"
        item = self._add_item(
            "cross-vehicle.mp4",
            age_days=180,
            sidecars=True,
            source_key=source_key,
        )
        primary = self.engine.archive_root / item["relative_path"]
        partial = primary.with_suffix(primary.suffix + ".part")
        partial_relative = str(partial.relative_to(self.engine.archive_root))
        other_source = "vehicle-two:recording:cross-vehicle.mp4:2"
        self.db.remember_recording_download_jobs(
            "vehicle-two",
            {other_source: {"filename": "cross-vehicle.mp4"}},
            {other_source: partial_relative},
        )

        self.assertFalse(
            self.engine._discard_vanished_recording_partial(
                partial_relative,
                source_key=source_key,
            )
        )
        result = self.engine.apply_retention(
            self._save_recording_policy(age_days=1)
        )

        self.assertEqual(result["deleted_items"], 0)
        self.assertTrue(primary.is_file())
        self.assertTrue(partial.is_file())
        self.assertTrue(partial.with_name(partial.name + ".meta").is_file())
        self.assertIsNotNone(self.db.get_item_by_source_key(source_key))

    def test_pending_retention_cleanup_restores_primary_for_cross_vehicle_job(
        self,
    ) -> None:
        source_key = "vehicle-one:recording:journal-cross-vehicle.mp4:1"
        item = self._add_item(
            "journal-cross-vehicle.mp4",
            age_days=180,
            sidecars=True,
            source_key=source_key,
        )
        item_id = int(item["id"])
        primary = self.engine.archive_root / item["relative_path"]
        partial = primary.with_suffix(primary.suffix + ".part")
        staged = primary.with_name(
            f".retention-{item_id}-{'d' * 24}.pending"
        )
        self.assertIsNotNone(
            self.db.prepare_retention_deletion(
                item_id,
                str(staged.relative_to(self.engine.archive_root)),
            )
        )
        primary.replace(staged)
        self.assertTrue(self.db.delete_archive_item(item_id))
        other_source = "vehicle-two:recording:journal-cross-vehicle.mp4:2"
        self.db.remember_recording_download_jobs(
            "vehicle-two",
            {other_source: {"filename": "journal-cross-vehicle.mp4"}},
            {
                other_source: str(
                    partial.relative_to(self.engine.archive_root)
                )
            },
        )

        self.assertEqual(self.engine._recover_retention_deletions(), 1)

        self.assertTrue(primary.is_file())
        self.assertFalse(staged.exists())
        self.assertTrue(partial.is_file())
        self.assertEqual(len(self.db.list_retention_deletion_jobs()), 1)

    def test_ownership_conflict_marker_blocks_retention(self) -> None:
        source_key = "vehicle-one:recording:marked-conflict.mp4:1"
        item = self._add_item(
            "marked-conflict.mp4",
            age_days=180,
            sidecars=True,
            source_key=source_key,
        )
        primary = self.engine.archive_root / item["relative_path"]
        partial = primary.with_suffix(primary.suffix + ".part")
        marker = partial.with_name(
            partial.name + ".ownership-conflict.json"
        )
        marker.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source_identities": [
                        source_key,
                        "vehicle-two:recording:marked-conflict.mp4:2",
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = self.engine.apply_retention(
            self._save_recording_policy(age_days=1)
        )

        self.assertEqual(result["deleted_items"], 0)
        self.assertTrue(primary.is_file())
        self.assertTrue(partial.is_file())
        self.assertTrue(marker.is_file())
        self.assertIsNotNone(self.db.get_item_by_source_key(source_key))
        self.assertIn(
            marker,
            self.engine._retention_sidecar_paths(primary, "recordings"),
        )

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

    def test_pinned_latest_item_occupies_a_keep_latest_slot(self) -> None:
        oldest = self._add_item("oldest.mp4", age_days=30)
        middle = self._add_item("middle.mp4", age_days=20)
        pinned_latest = self._add_item("pinned-latest.mp4", age_days=10)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO archive_retention_protections(
                    source_key,category,protected_at
                ) VALUES(?,?,?)
                """,
                (
                    pinned_latest["source_key"],
                    "recordings",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        settings = self._save_recording_policy(age_days=1, keep_latest=1)

        result = self.engine.apply_retention(settings)

        self.assertEqual(result["deleted_items"], 2)
        self.assertTrue(self.db.is_retention_tombstoned(oldest["source_key"]))
        self.assertTrue(self.db.is_retention_tombstoned(middle["source_key"]))
        self.assertFalse(
            self.db.is_retention_tombstoned(pinned_latest["source_key"])
        )
        self.assertTrue(self.db.is_retention_protected(pinned_latest["source_key"]))
        self.assertTrue(
            (self.engine.archive_root / pinned_latest["relative_path"]).exists()
        )

    def test_very_large_age_window_saturates_without_datetime_underflow(self) -> None:
        item = self._add_item("within-huge-window.mp4", age_days=180)
        settings = self._save_recording_policy(age_days=1_000_000)

        result = self.engine.apply_retention(settings)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["deleted_items"], 0)
        self.assertFalse(self.db.is_retention_tombstoned(item["source_key"]))
        self.assertTrue((self.engine.archive_root / item["relative_path"]).exists())

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
