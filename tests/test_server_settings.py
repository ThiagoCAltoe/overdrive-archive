from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.db import Database
from app.server import Handler
from app.sync import SyncEngine


class _RetentionEngine:
    def __init__(self) -> None:
        self.calls = []

    def apply_retention(self, settings):
        self.calls.append(settings)
        return {"status": "complete", "deleted_items": 0}

    def update_settings_and_apply_retention(self, update):
        saved = update()
        return saved, self.apply_retention(saved)


class _ObservedLock:
    def __init__(self, thread_name: str, waiting: threading.Event) -> None:
        self._lock = threading.Lock()
        self._thread_name = thread_name
        self._waiting = waiting

    def acquire(self, blocking: bool = True) -> bool:
        if threading.current_thread().name == self._thread_name:
            self._waiting.set()
        return self._lock.acquire(blocking)

    def release(self) -> None:
        self._lock.release()


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

    def test_concurrent_settings_updates_cannot_apply_stale_retention(self) -> None:
        engine = SyncEngine(self.db, self.archive_root)
        first_retention_started = threading.Event()
        release_first_retention = threading.Event()
        second_waiting_for_lock = threading.Event()
        setattr(
            engine,
            "_retention_lock",
            _ObservedLock("disable-retention", second_waiting_for_lock),
        )
        server = SimpleNamespace(
            db=self.db,
            engine=engine,
            archive_root=self.archive_root,
        )
        applied_states: list[bool] = []
        errors: list[BaseException] = []
        original_apply = engine._apply_retention_locked

        def paused_apply(settings):
            enabled = bool(
                settings["retention"]["categories"]["recordings"]["enabled"]
            )
            applied_states.append(enabled)
            if enabled:
                first_retention_started.set()
                if not release_first_retention.wait(2):
                    raise TimeoutError("test did not release the first retention")
            return original_apply(settings)

        def make_handler(payload):
            handler = object.__new__(Handler)
            handler.server = server
            handler._read_json = lambda: payload
            handler._storage_runtime = lambda: {
                "storage_capacity_bytes": 10_000,
                "storage_free_bytes": 10_000,
                "storage_used_bytes": 0,
            }
            responses = []
            handler._json = lambda status, body: responses.append((status, body))
            return handler, responses

        enable_handler, enable_responses = make_handler(
            {
                "retention": {
                    "categories": {
                        "recordings": {
                            "enabled": True,
                            "value": 1,
                            "unit": "days",
                        }
                    }
                }
            }
        )
        disable_handler, disable_responses = make_handler(
            {
                "retention": {
                    "categories": {"recordings": {"enabled": False}}
                }
            }
        )

        def run(handler):
            try:
                handler._handle_settings_update()
            except BaseException as exc:
                errors.append(exc)

        with patch.object(
            engine,
            "_apply_retention_locked",
            side_effect=paused_apply,
        ):
            enabling = threading.Thread(target=run, args=(enable_handler,))
            disabling = threading.Thread(
                target=run,
                args=(disable_handler,),
                name="disable-retention",
            )
            enabling.start()
            self.assertTrue(first_retention_started.wait(1))
            disabling.start()
            self.assertTrue(second_waiting_for_lock.wait(1))

            # The second request has reached the same lock, but its SAVE is
            # still blocked behind the first request's retention application.
            self.assertTrue(
                self.db.get_settings()["retention"]["categories"][
                    "recordings"
                ]["enabled"]
            )
            self.assertFalse(disable_responses)

            release_first_retention.set()
            enabling.join(2)
            disabling.join(2)

        self.assertFalse(enabling.is_alive())
        self.assertFalse(disabling.is_alive())
        self.assertFalse(errors)
        self.assertEqual([response[0] for response in enable_responses], [200])
        self.assertEqual([response[0] for response in disable_responses], [200])
        self.assertEqual(applied_states, [True, False])
        self.assertEqual(disable_responses[0][1]["retention"]["status"], "disabled")
        self.assertFalse(
            self.db.get_settings()["retention"]["categories"]["recordings"][
                "enabled"
            ]
        )


if __name__ == "__main__":
    unittest.main()
