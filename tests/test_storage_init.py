from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.storage_init import (
    _OWNER_MARKER,
    _repair_ownership,
    prepare_path,
)


class StorageInitializationTests(unittest.TestCase):
    def test_writable_unmarked_volume_still_migrates_legacy_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive"
            path.mkdir()

            with (
                patch("app.storage_init._can_write_as", return_value=True),
                patch("app.storage_init._repair_ownership") as repair,
                patch("app.storage_init._write_owner_marker_as") as write_marker,
            ):
                prepare_path(path, 12001, 12002)

            repair.assert_called_once_with(path, 12001, 12002)
            write_marker.assert_called_once_with(path, 12001, 12002)

    def test_matching_marker_skips_recursive_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive"
            path.mkdir()
            (path / _OWNER_MARKER).write_text("12001:12002\n", encoding="ascii")

            with (
                patch("app.storage_init._can_write_as", return_value=True),
                patch("app.storage_init._repair_ownership") as repair,
            ):
                prepare_path(path, 12001, 12002)

            repair.assert_not_called()

    def test_recursive_migration_repairs_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive"
            nested = path / "vehicle" / "recordings"
            nested.mkdir(parents=True)
            recording = nested / "clip.mp4"
            recording.write_bytes(b"video")

            with patch("app.storage_init.os.chown") as chown:
                _repair_ownership(path, 12001, 12002)

            migrated = {
                call.args[0]
                for call in chown.call_args_list
            }
            self.assertEqual(
                migrated,
                {path, path / "vehicle", nested, recording},
            )
            self.assertTrue(
                all(
                    call.kwargs == {"follow_symlinks": False}
                    for call in chown.call_args_list
                )
            )


if __name__ == "__main__":
    unittest.main()
