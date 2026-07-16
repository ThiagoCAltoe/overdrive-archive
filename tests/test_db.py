from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
