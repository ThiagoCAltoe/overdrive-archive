from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.db import Database
from app.server import Handler


class _RetentionEngine:
    def __init__(self) -> None:
        self.calls = []

    def apply_retention(self, settings):
        self.calls.append(settings)
        return {"status": "complete", "deleted_items": 0}


class SettingsHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.archive_root = root / "archive"
        self.archive_root.mkdir()
        self.db = Database(root / "data" / "archive.sqlite3")
        self.engine = _RetentionEngine()
        self.handler = object.__new__(Handler)
        self.handler.server = SimpleNamespace(
            db=self.db,
            engine=self.engine,
            archive_root=self.archive_root,
        )
        self.responses = []
        self.handler._json = lambda status, payload: self.responses.append(
            (status, payload)
        )

    def test_storage_runtime_reports_the_archive_filesystem_capacity(self) -> None:
        runtime = self.handler._storage_runtime()

        self.assertGreater(runtime["storage_capacity_bytes"], 0)
        self.assertGreaterEqual(runtime["storage_free_bytes"], 0)
        self.assertGreaterEqual(runtime["storage_used_bytes"], 0)
        self.assertLessEqual(
            runtime["storage_free_bytes"],
            runtime["storage_capacity_bytes"],
        )

    def test_settings_reject_a_limit_above_the_mounted_capacity(self) -> None:
        self.handler._read_json = lambda: {
            "retention": {
                "storage_limit": {"enabled": True, "max_bytes": 101}
            }
        }
        self.handler._storage_runtime = lambda: {
            "storage_capacity_bytes": 100,
            "storage_free_bytes": 50,
            "storage_used_bytes": 50,
        }

        self.handler._handle_settings_update()

        self.assertEqual(self.responses[0][0], 400)
        self.assertIn("cannot exceed", self.responses[0][1]["error"])
        self.assertFalse(self.engine.calls)
        self.assertFalse(
            self.db.get_settings()["retention"]["storage_limit"]["enabled"]
        )

    def test_saving_retention_applies_it_immediately_when_idle(self) -> None:
        self.handler._read_json = lambda: {
            "retention": {
                "categories": {
                    "recordings": {
                        "enabled": True,
                        "value": 12,
                        "unit": "hours",
                        "keep_latest_enabled": True,
                        "keep_latest_count": 3,
                    }
                },
                "storage_limit": {"enabled": True, "max_bytes": 50},
            }
        }
        self.handler._storage_runtime = lambda: {
            "storage_capacity_bytes": 100,
            "storage_free_bytes": 50,
            "storage_used_bytes": 50,
        }

        self.handler._handle_settings_update()

        status, payload = self.responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["retention"]["status"], "complete")
        self.assertEqual(len(self.engine.calls), 1)
        rule = self.db.get_settings()["retention"]["categories"]["recordings"]
        self.assertEqual(rule["value"], 12)
        self.assertEqual(rule["unit"], "hours")
        self.assertEqual(rule["keep_latest_count"], 3)


if __name__ == "__main__":
    unittest.main()
