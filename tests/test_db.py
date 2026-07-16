from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import Database


class DatabasePermissionTests(unittest.TestCase):
    def test_new_data_directory_and_sqlite_files_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary) / "private-data"
            path = data_dir / "archive.sqlite3"
            database = Database(path)

            self.assertEqual(stat.S_IMODE(data_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            sidecars = (Path(f"{path}-wal"), Path(f"{path}-shm"))
            for sidecar in sidecars:
                sidecar.write_bytes(b"test")
                os.chmod(sidecar, 0o644)
            database._harden_permissions()

            for sidecar in sidecars:
                self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)

    def test_library_orders_by_effective_recorded_or_archive_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Database(Path(temporary) / "archive.sqlite3")
            common = {
                "category": "recordings",
                "subtype": "drive",
                "vehicle": "test-vehicle",
                "relative_path": "vehicles/test-vehicle/item",
                "media_type": "video/mp4",
                "size_bytes": 1,
                "sha256": "0" * 64,
                "metadata": {},
            }
            database.add_item(
                source_key="milliseconds",
                filename="milliseconds.mp4",
                source_timestamp=1_700_000_000_000,
                **common,
            )
            database.add_item(
                source_key="archive-time",
                filename="archive-time.json",
                source_timestamp=None,
                **{**common, "category": "telemetry", "subtype": ""},
            )
            database.add_item(
                source_key="seconds",
                filename="seconds.mp4",
                source_timestamp=1_800_000_000,
                **common,
            )
            with database.connect() as conn:
                conn.execute(
                    """
                    UPDATE archive_items
                       SET created_at='2024-01-01T00:00:00+00:00'
                     WHERE source_key='archive-time'
                    """
                )

            items = database.list_items()

            self.assertEqual(
                [item["filename"] for item in items],
                [
                    "seconds.mp4",
                    "archive-time.json",
                    "milliseconds.mp4",
                ],
            )


class RecordingDownloadJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Database(
            Path(self.temporary.name) / "archive.sqlite3"
        )

    def test_batch_remember_is_canonical_and_reports_preexisting_keys(self) -> None:
        with patch("app.db.utc_now", return_value="2026-07-16T13:00:00+00:00"):
            known = self.database.remember_recording_download_jobs(
                "vehicle-one",
                {
                    "source-b": {"z": 1, "name": "câmera"},
                    "source-a": {"nested": {"b": 2, "a": 1}},
                },
            )
        self.assertEqual(known, set())

        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT item_json,first_seen_at,last_seen_at
                  FROM recording_download_jobs WHERE source_key='source-b'
                """
            ).fetchone()
        self.assertEqual(row["item_json"], '{"name":"câmera","z":1}')
        self.assertEqual(row["first_seen_at"], "2026-07-16T13:00:00+00:00")
        self.assertEqual(row["last_seen_at"], "2026-07-16T13:00:00+00:00")

        with patch("app.db.utc_now", return_value="2026-07-16T14:00:00+00:00"):
            known = self.database.remember_recording_download_jobs(
                "vehicle-one",
                {
                    "source-b": {"z": 2},
                    "source-c": {"z": 3},
                },
            )
        self.assertEqual(known, {"source-b"})

        with self.database.connect() as conn:
            rows = {
                row["source_key"]: dict(row)
                for row in conn.execute(
                    """
                    SELECT source_key,item_json,first_seen_at,last_seen_at
                      FROM recording_download_jobs
                    """
                )
            }
        self.assertEqual(rows["source-b"]["item_json"], '{"z":2}')
        self.assertEqual(
            rows["source-b"]["first_seen_at"],
            "2026-07-16T13:00:00+00:00",
        )
        self.assertEqual(
            rows["source-b"]["last_seen_at"],
            "2026-07-16T14:00:00+00:00",
        )
        self.assertEqual(
            rows["source-c"]["first_seen_at"],
            "2026-07-16T14:00:00+00:00",
        )

    def test_list_is_vehicle_scoped_and_returns_decoded_items(self) -> None:
        self.database.remember_recording_download_jobs(
            "vehicle-one", {"one": {"filename": "one.mp4"}}
        )
        self.database.remember_recording_download_jobs(
            "vehicle-two", {"two": {"filename": "two.mp4"}}
        )

        jobs = self.database.list_recording_download_jobs("vehicle-one")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source_key"], "one")
        self.assertEqual(jobs[0]["vehicle_identity"], "vehicle-one")
        self.assertEqual(jobs[0]["item"], {"filename": "one.mp4"})
        self.assertIn("first_seen_at", jobs[0])
        self.assertIn("last_seen_at", jobs[0])

    def test_bad_item_rejects_the_entire_discovery_batch(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid JSON values"):
            self.database.remember_recording_download_jobs(
                "vehicle-one",
                {
                    "valid": {"filename": "valid.mp4"},
                    "invalid": {"value": float("nan")},
                },
            )

        self.assertEqual(
            self.database.list_recording_download_jobs("vehicle-one"), []
        )

    def test_source_key_cannot_be_reassigned_to_another_vehicle(self) -> None:
        self.database.remember_recording_download_jobs(
            "vehicle-one", {"same-key": {"filename": "one.mp4"}}
        )

        with self.assertRaisesRegex(ValueError, "another vehicle"):
            self.database.remember_recording_download_jobs(
                "vehicle-two", {"same-key": {"filename": "two.mp4"}}
            )

        jobs = self.database.list_recording_download_jobs("vehicle-one")
        self.assertEqual(jobs[0]["item"]["filename"], "one.mp4")

    def test_delete_and_complete_remove_jobs_by_source_key(self) -> None:
        self.database.remember_recording_download_jobs(
            "vehicle-one",
            {
                "delete-me": {"filename": "delete.mp4"},
                "complete-me": {"filename": "complete.mp4"},
            },
        )

        self.assertTrue(
            self.database.delete_recording_download_job("delete-me")
        )
        self.assertFalse(
            self.database.delete_recording_download_job("delete-me")
        )
        self.assertTrue(
            self.database.complete_recording_download_job("complete-me")
        )
        self.assertEqual(
            self.database.list_recording_download_jobs("vehicle-one"), []
        )


class RetentionDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Database(
            Path(self.temporary.name) / "archive.sqlite3"
        )

    def add_item(
        self,
        source_key: str,
        *,
        category: str = "recordings",
        source_timestamp: int | None = None,
    ) -> int:
        added = self.database.add_item(
            source_key=source_key,
            category=category,
            subtype="drive" if category == "recordings" else "",
            vehicle="vehicle-one",
            filename=f"{source_key}.dat",
            relative_path=f"vehicles/vehicle-one/{source_key}.dat",
            media_type="application/octet-stream",
            size_bytes=10,
            sha256="0" * 64,
            source_timestamp=source_timestamp,
            metadata={"source": source_key},
        )
        self.assertTrue(added)
        row = self.database.get_item_by_source_key(source_key)
        self.assertIsNotNone(row)
        return int(row["id"])

    def test_candidates_are_complete_and_ordered_by_local_archive_age(self) -> None:
        newest_source_time = self.add_item(
            "first-inserted", source_timestamp=2_000_000_000_000
        )
        second_id = self.add_item(
            "second-inserted", source_timestamp=1
        )
        third_id = self.add_item("third-inserted", category="telemetry")
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE archive_items SET created_at=? WHERE id=?",
                ("2026-07-14T00:00:00+00:00", newest_source_time),
            )
            conn.execute(
                "UPDATE archive_items SET created_at=? WHERE id IN (?,?)",
                ("2026-07-15T00:00:00+00:00", second_id, third_id),
            )

        candidates = self.database.list_retention_candidates()

        self.assertEqual(
            [candidate["source_key"] for candidate in candidates],
            ["first-inserted", "second-inserted", "third-inserted"],
        )
        expected_columns = {
            "id",
            "source_key",
            "category",
            "subtype",
            "vehicle",
            "filename",
            "relative_path",
            "media_type",
            "size_bytes",
            "sha256",
            "source_timestamp",
            "metadata_json",
            "created_at",
        }
        self.assertEqual(set(candidates[0]), expected_columns)

    def test_candidates_can_be_filtered_by_category(self) -> None:
        self.add_item("video", category="recordings")
        self.add_item("snapshot", category="telemetry")

        candidates = self.database.list_retention_candidates("recordings")

        self.assertEqual(
            [candidate["source_key"] for candidate in candidates], ["video"]
        )

    def test_delete_removes_only_inventory_row_and_never_touches_file(self) -> None:
        item_id = self.add_item("delete-row")
        keep_id = self.add_item("keep-row")
        media = Path(self.temporary.name) / "delete-row.dat"
        media.write_bytes(b"must remain")

        self.assertTrue(self.database.delete_archive_item(item_id))
        self.assertFalse(self.database.delete_archive_item(item_id))
        self.assertFalse(self.database.delete_archive_item(True))
        self.assertTrue(media.is_file())
        self.assertIsNone(self.database.get_item(item_id))
        self.assertIsNotNone(self.database.get_item(keep_id))

    def test_deleted_item_is_tombstoned_and_remains_known(self) -> None:
        item_id = self.add_item("retained-source", category="telemetry")
        self.assertTrue(self.database.has_item("retained-source"))
        self.assertFalse(
            self.database.is_retention_tombstoned("retained-source")
        )

        with patch("app.db.utc_now", return_value="2026-07-16T15:00:00+00:00"):
            self.assertTrue(self.database.delete_archive_item(item_id))

        self.assertIsNone(
            self.database.get_item_by_source_key("retained-source")
        )
        self.assertTrue(self.database.has_item("retained-source"))
        self.assertTrue(
            self.database.is_retention_tombstoned("retained-source")
        )
        with self.database.connect() as conn:
            tombstone = conn.execute(
                """
                SELECT category,deleted_at
                  FROM archive_retention_tombstones WHERE source_key=?
                """,
                ("retained-source",),
            ).fetchone()
        self.assertEqual(tombstone["category"], "telemetry")
        self.assertEqual(
            tombstone["deleted_at"], "2026-07-16T15:00:00+00:00"
        )

    def test_tombstone_and_row_delete_are_atomic(self) -> None:
        item_id = self.add_item("rollback-source")
        with self.database.connect() as conn:
            conn.execute(
                """
                CREATE TRIGGER reject_retention_delete
                BEFORE DELETE ON archive_items
                BEGIN
                    SELECT RAISE(ABORT, 'blocked for test');
                END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.database.delete_archive_item(item_id)

        self.assertIsNotNone(self.database.get_item(item_id))
        self.assertFalse(
            self.database.is_retention_tombstoned("rollback-source")
        )

    def test_missing_item_does_not_create_a_tombstone(self) -> None:
        self.assertFalse(self.database.delete_archive_item(999_999))
        with self.database.connect() as conn:
            count = conn.execute(
                "SELECT count(*) FROM archive_retention_tombstones"
            ).fetchone()[0]
        self.assertEqual(count, 0)


class RestorableRetentionDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Database(
            Path(self.temporary.name) / "archive.sqlite3"
        )

    def retain_recording(
        self,
        vehicle_identity: str,
        filename: str,
        timestamp: int,
        *,
        subtype: str = "drive",
        vehicle: str = "Test vehicle",
        size_bytes: int = 100,
    ) -> str:
        source_key = (
            f"{vehicle_identity}:recording:{filename}:{timestamp}"
        )
        added = self.database.add_item(
            source_key=source_key,
            category="recordings",
            subtype=subtype,
            vehicle=vehicle,
            filename=filename,
            relative_path=f"vehicles/test/recordings/{filename}",
            media_type="video/mp4",
            size_bytes=size_bytes,
            sha256="a" * 64,
            source_timestamp=timestamp,
            metadata={"filename": filename, "type": subtype, "z": 1},
        )
        self.assertTrue(added)
        row = self.database.get_item_by_source_key(source_key)
        self.assertIsNotNone(row)
        self.assertTrue(self.database.delete_archive_item(int(row["id"])))
        return source_key

    def test_legacy_tombstone_table_is_migrated_and_backfilled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.sqlite3"
            source_key = "vehicle-legacy:recording:replay_clip.mp4:12345"
            with sqlite3.connect(path) as conn:
                conn.execute(
                    """
                    CREATE TABLE archive_retention_tombstones(
                        source_key TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        deleted_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO archive_retention_tombstones(
                        source_key,category,deleted_at
                    ) VALUES(?,?,?)
                    """,
                    (source_key, "recordings", "2026-07-15T10:00:00+00:00"),
                )

            migrated = Database(path)
            with migrated.connect() as conn:
                columns = {
                    row["name"]
                    for row in conn.execute(
                        "PRAGMA table_info(archive_retention_tombstones)"
                    )
                }
                row = conn.execute(
                    """
                    SELECT * FROM archive_retention_tombstones
                     WHERE source_key=?
                    """,
                    (source_key,),
                ).fetchone()

            self.assertTrue(
                {
                    "vehicle_identity",
                    "vehicle",
                    "filename",
                    "subtype",
                    "source_timestamp",
                    "remote_size_bytes",
                    "item_json",
                    "last_seen_at",
                    "restore_requested_at",
                }.issubset(columns)
            )
            self.assertEqual(row["vehicle_identity"], "vehicle-legacy")
            self.assertEqual(row["filename"], "replay_clip.mp4")
            self.assertEqual(row["subtype"], "replay")
            self.assertEqual(row["source_timestamp"], 12345)
            self.assertEqual(row["remote_size_bytes"], 0)
            self.assertEqual(row["item_json"], "{}")
            self.assertEqual(row["last_seen_at"], row["deleted_at"])

    def test_reconcile_updates_live_purges_missing_and_is_vehicle_scoped(self) -> None:
        keep = self.retain_recording(
            "vehicle-one", "keep.mp4", 100, size_bytes=100
        )
        missing = self.retain_recording(
            "vehicle-one", "missing.mp4", 200
        )
        other = self.retain_recording(
            "vehicle-two", "other.mp4", 300
        )
        self.database.remember_recording_download_jobs(
            "vehicle-one", {missing: {"filename": "missing.mp4"}}
        )

        with patch("app.db.utc_now", return_value="2026-07-16T16:00:00+00:00"):
            result = self.database.reconcile_recording_tombstones(
                "vehicle-one",
                {
                    keep: {
                        "filename": "keep.mp4",
                        "type": "replay",
                        "timestamp": 100,
                        "size": 999,
                        "remote": {"metadata": True},
                    }
                },
            )

        self.assertEqual(result, {"updated": 1, "purged": 1})
        self.assertTrue(self.database.is_retention_tombstoned(keep))
        self.assertFalse(self.database.is_retention_tombstoned(missing))
        self.assertTrue(self.database.is_retention_tombstoned(other))
        self.assertEqual(
            self.database.list_recording_download_jobs("vehicle-one"), []
        )
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT subtype,remote_size_bytes,item_json,last_seen_at
                  FROM archive_retention_tombstones WHERE source_key=?
                """,
                (keep,),
            ).fetchone()
        self.assertEqual(row["subtype"], "replay")
        self.assertEqual(row["remote_size_bytes"], 999)
        self.assertEqual(row["last_seen_at"], "2026-07-16T16:00:00+00:00")
        self.assertEqual(
            json.loads(row["item_json"])["remote"], {"metadata": True}
        )

        result = self.database.reconcile_recording_tombstones(
            "vehicle-one", {}
        )
        self.assertEqual(result, {"updated": 0, "purged": 1})
        self.assertFalse(self.database.is_retention_tombstoned(keep))
        self.assertTrue(self.database.is_retention_tombstoned(other))

    def test_failed_reconcile_does_not_apply_a_partial_batch(self) -> None:
        first = self.retain_recording("vehicle-one", "first.mp4", 1)
        second = self.retain_recording("vehicle-one", "second.mp4", 2)
        before = self.database.list_deleted_recordings()

        with self.assertRaisesRegex(ValueError, "another vehicle"):
            self.database.reconcile_recording_tombstones(
                "vehicle-one",
                {
                    first: {"filename": "first.mp4", "size": 777},
                    "vehicle-two:recording:foreign.mp4:3": {
                        "filename": "foreign.mp4"
                    },
                },
            )

        after = self.database.list_deleted_recordings()
        self.assertEqual(after, before)
        self.assertTrue(self.database.is_retention_tombstoned(first))
        self.assertTrue(self.database.is_retention_tombstoned(second))

    def test_deleted_placeholders_have_remote_not_local_size_and_filters(self) -> None:
        replay = self.retain_recording(
            "vehicle-one",
            "replay_trip.mp4",
            50,
            subtype="replay",
            vehicle="Blue Dolphin",
            size_bytes=4096,
        )
        self.retain_recording(
            "vehicle-one", "drive_trip.mp4", 60, subtype="drive"
        )

        rows = self.database.list_deleted_recordings(
            subtype="replay", search="Blue", limit=1
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_key"], replay)
        self.assertEqual(rows[0]["vehicle"], "Blue Dolphin")
        self.assertEqual(rows[0]["size_bytes"], 0)
        self.assertEqual(rows[0]["remote_size_bytes"], 4096)
        self.assertNotIn("item_json", rows[0])
        with self.database.connect() as conn:
            storage_type = conn.execute(
                """
                SELECT typeof(item_json) FROM archive_retention_tombstones
                 WHERE source_key=?
                """,
                (replay,),
            ).fetchone()[0]
        self.assertEqual(storage_type, "text")

    def test_restore_completion_creates_and_enforces_manual_protection(self) -> None:
        source_key = self.retain_recording(
            "vehicle-one", "restore.mp4", 500, size_bytes=2048
        )
        self.assertFalse(self.database.recording_restore_requested(source_key))
        self.assertFalse(self.database.complete_recording_restore(source_key))
        self.assertFalse(
            self.database.has_pending_recording_restores("vehicle-one")
        )

        with patch("app.db.utc_now", return_value="2026-07-16T17:00:00+00:00"):
            self.assertEqual(
                self.database.request_recording_restore(source_key),
                "vehicle-one",
            )
        self.assertTrue(self.database.recording_restore_requested(source_key))
        self.assertTrue(
            self.database.has_pending_recording_restores("vehicle-one")
        )
        self.assertFalse(
            self.database.has_pending_recording_restores("vehicle-two")
        )
        requested = self.database.list_deleted_recordings(search="restore")
        self.assertEqual(
            requested[0]["restore_requested_at"],
            "2026-07-16T17:00:00+00:00",
        )

        restored = self.database.add_item(
            source_key=source_key,
            category="recordings",
            subtype="drive",
            vehicle="Test vehicle",
            filename="restore.mp4",
            relative_path="vehicles/test/restore.mp4",
            media_type="video/mp4",
            size_bytes=2048,
            sha256="b" * 64,
            source_timestamp=500,
            metadata={"restored": True},
        )
        self.assertTrue(restored)
        self.assertTrue(self.database.complete_recording_restore(source_key))
        self.assertFalse(
            self.database.has_pending_recording_restores("vehicle-one")
        )
        self.assertFalse(self.database.is_retention_tombstoned(source_key))
        self.assertTrue(self.database.is_retention_protected(source_key))
        self.assertEqual(
            self.database.list_retention_protected_source_keys("recordings"),
            {source_key},
        )
        self.assertEqual(self.database.list_retention_candidates(), [])
        restored_row = self.database.get_item_by_source_key(source_key)
        self.assertFalse(
            self.database.delete_archive_item(int(restored_row["id"]))
        )

        self.assertTrue(self.database.clear_retention_protection(source_key))
        self.assertFalse(self.database.is_retention_protected(source_key))
        self.assertTrue(
            self.database.delete_archive_item(int(restored_row["id"]))
        )

    def test_restore_request_fails_after_remote_item_disappears(self) -> None:
        source_key = self.retain_recording(
            "vehicle-one", "gone.mp4", 700
        )
        self.database.reconcile_recording_tombstones("vehicle-one", {})

        self.assertFalse(self.database.request_recording_restore(source_key))
        self.assertFalse(self.database.recording_restore_requested(source_key))

if __name__ == "__main__":
    unittest.main()
