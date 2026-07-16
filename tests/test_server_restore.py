from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from app.db import RetentionCleanupPending
from app.server import ArchiveHTTPServer, Handler, SESSION_COOKIE


class _Auth:
    def validate_session(self, token: str) -> bool:
        return token == "valid-session"


class _Database:
    def __init__(self) -> None:
        self.restore_exists = True
        self.cleanup_pending = False
        self.restore_identity = "vehicle:test"
        self.restore_requests: list[str] = []
        self.deleted_filters: list[dict] = []
        self.released: list[str] = []
        self.archived_item = {
            "id": 1,
            "source_key": "vehicle:test:recording:available.mp4:100",
            "category": "recordings",
        }

    def list_library_items(self, **filters) -> list[dict]:
        self.deleted_filters.append(dict(filters))
        if filters.get("category") == "trips":
            return []
        archived = {
            "id": 1,
            "source_key": self.archived_item["source_key"],
            "category": "recordings",
            "subtype": "drive",
            "filename": "available.mp4",
            "relative_path": "vehicles/test/available.mp4",
            "media_type": "video/mp4",
            "size_bytes": 10,
            "source_timestamp": 100,
            "metadata_json": "{}",
            "retention_protected": True,
            "deleted_local": False,
        }
        deleted = {
            "source_key": "vehicle:test:recording:deleted.mp4:123",
            "category": "recordings",
            "subtype": "replay",
            "vehicle": "test-vehicle",
            "filename": "deleted.mp4",
            "source_timestamp": 123,
            "remote_size_bytes": 456,
            "deleted_at": "2026-07-16T18:00:00+00:00",
            "last_seen_at": "2026-07-16T17:00:00+00:00",
            "restore_requested_at": "",
            "cleanup_pending": self.cleanup_pending,
            "internal_value": "must-not-leak",
            "deleted_local": True,
        }
        rows = (
            [deleted]
            if filters.get("subtype") == "replay"
            else [deleted, archived]
        )
        offset = int(filters.get("offset") or 0)
        limit = int(filters.get("limit") or 100)
        return rows[offset : offset + limit]

    def recording_subtypes(self) -> list[dict]:
        return []

    def request_recording_restore(self, source_key: str) -> str | None:
        self.restore_requests.append(source_key)
        if self.cleanup_pending:
            raise RetentionCleanupPending("cleanup pending for test")
        return self.restore_identity if self.restore_exists else None

    def get_item(self, item_id: int):
        return dict(self.archived_item) if item_id == 1 else None

    def clear_retention_protection(self, source_key: str) -> bool:
        self.released.append(source_key)
        return source_key == self.archived_item["source_key"]

    @staticmethod
    def get_settings() -> dict:
        return {}


class _Engine:
    def __init__(self) -> None:
        self.start_sync = True
        self.current_identity = "vehicle:test"
        self.identity_requires_probe = False
        self.triggers: list[str] = []
        self.retention_calls: list[dict] = []

    def trigger(self, reason: str) -> bool:
        self.triggers.append(reason)
        return self.start_sync

    def configured_vehicle_identity(self) -> str:
        return self.current_identity

    def can_start_recording_restore(self, restore_identity: str) -> bool:
        return (
            restore_identity == self.current_identity
            or self.identity_requires_probe
        )

    def apply_retention(self, settings: dict) -> dict:
        self.retention_calls.append(settings)
        return {"status": "complete", "deleted_items": 0}


class RecordingRestoreServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "archive"
        self.root.mkdir()
        self.database = _Database()
        self.engine = _Engine()
        self.server = ArchiveHTTPServer(
            ("127.0.0.1", 0),
            Handler,
            db=self.database,
            engine=self.engine,
            archive_root=self.root,
            auth=_Auth(),
            secure_cookies=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.addCleanup(self._stop_server)

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        authenticated: bool = True,
        origin: str | None = None,
    ) -> tuple[int, dict]:
        host, port = self.server.server_address
        connection = HTTPConnection(host, port, timeout=2)
        headers: dict[str, str] = {}
        body: bytes | None = None
        if authenticated:
            headers["Cookie"] = f"{SESSION_COOKIE}=valid-session"
        if origin is not None:
            headers["Origin"] = origin
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_items_append_safe_deleted_recording_placeholders(self) -> None:
        status, payload = self._request(
            "GET",
            "/api/items?subtype=replay&q=deleted&limit=25",
        )

        self.assertEqual(status, 200)
        self.assertEqual(
            self.database.deleted_filters,
            [
                {
                    "category": "",
                    "subtype": "replay",
                    "search": "deleted",
                    "limit": 26,
                    "offset": 0,
                }
            ],
        )
        deleted = payload["items"][0]
        self.assertTrue(deleted["deleted_local"])
        self.assertEqual(
            deleted["source_key"],
            "vehicle:test:recording:deleted.mp4:123",
        )
        self.assertIsNone(deleted["id"])
        self.assertEqual(deleted["vehicle"], "test-vehicle")
        self.assertEqual(deleted["remote_size_bytes"], 456)
        self.assertIsNone(deleted["thumbnail_url"])
        self.assertIsNone(deleted["media_url"])
        self.assertFalse(deleted["cleanup_pending"])
        self.assertNotIn("relative_path", deleted)
        self.assertNotIn("internal_value", deleted)

    def test_items_filters_the_unified_library_for_other_categories(self) -> None:
        status, _payload = self._request("GET", "/api/items?category=trips")

        self.assertEqual(status, 200)
        self.assertEqual(
            self.database.deleted_filters,
            [
                {
                    "category": "trips",
                    "subtype": "",
                    "search": "",
                    "limit": 101,
                    "offset": 0,
                }
            ],
        )

    def test_restore_queues_and_starts_a_sync(self) -> None:
        host, port = self.server.server_address
        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "  recording-source  "},
            origin=f"http://{host}:{port}",
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload, {"queued": True, "sync_started": True})
        self.assertEqual(self.database.restore_requests, ["recording-source"])
        self.assertEqual(self.engine.triggers, ["restore"])

    def test_restore_remains_queued_while_a_sync_is_active(self) -> None:
        self.engine.start_sync = False

        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "recording-source"},
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload, {"queued": True, "sync_started": False})
        self.assertEqual(self.engine.triggers, ["restore"])

    def test_restore_for_another_vehicle_does_not_start_a_useless_sync(self) -> None:
        self.database.restore_identity = "vehicle:other"

        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "recording-source"},
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload, {"queued": True, "sync_started": False})
        self.assertEqual(self.database.restore_requests, ["recording-source"])
        self.assertEqual(self.engine.triggers, [])

    def test_restore_starts_an_identity_probe_when_saved_identity_is_uncertain(
        self,
    ) -> None:
        self.database.restore_identity = "vehicle:observed"
        self.engine.identity_requires_probe = True

        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "recording-source"},
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload, {"queued": True, "sync_started": True})
        self.assertEqual(self.engine.triggers, ["restore"])

    def test_restore_returns_not_found_without_triggering_sync(self) -> None:
        self.database.restore_exists = False

        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "missing-source"},
        )

        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "Deleted recording not found."})
        self.assertEqual(self.engine.triggers, [])

    def test_restore_reports_pending_local_cleanup_as_a_conflict(self) -> None:
        self.database.cleanup_pending = True

        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "recording-source"},
        )

        self.assertEqual(status, 409)
        self.assertEqual(payload["code"], "retention_cleanup_pending")
        self.assertIn("cleanup is still in progress", payload["error"])
        self.assertEqual(self.database.restore_requests, ["recording-source"])
        self.assertEqual(self.engine.triggers, [])

    def test_restore_requires_authentication(self) -> None:
        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "recording-source"},
            authenticated=False,
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload, {"error": "Authentication required."})
        self.assertEqual(self.database.restore_requests, [])

    def test_restore_rejects_cross_origin_requests(self) -> None:
        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "recording-source"},
            origin="https://attacker.invalid",
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload, {"error": "Cross-origin request rejected."})
        self.assertEqual(self.database.restore_requests, [])

    def test_restore_rejects_an_oversized_source_key(self) -> None:
        status, payload = self._request(
            "POST",
            "/api/recordings/restore",
            payload={"source_key": "x" * 1001},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload, {"error": "A valid source_key is required."})
        self.assertEqual(self.database.restore_requests, [])

    def test_release_restored_recording_back_to_retention(self) -> None:
        status, payload = self._request(
            "POST",
            "/api/recordings/release-retention",
            payload={"item_id": 1},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["released"])
        self.assertFalse(payload["item_deleted"])
        self.assertEqual(
            self.database.released,
            ["vehicle:test:recording:available.mp4:100"],
        )
        self.assertEqual(self.engine.retention_calls, [{}])


if __name__ == "__main__":
    unittest.main()
