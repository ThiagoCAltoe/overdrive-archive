from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import Mock, patch

from app.server import ArchiveHTTPServer, Handler, SESSION_COOKIE


class _Auth:
    def validate_session(self, token: str) -> bool:
        return token == "valid-session"


class _Engine:
    def __init__(self, stopping: bool) -> None:
        self.stopping = stopping
        self.stop_requests = 0

    def request_stop(self) -> bool:
        self.stop_requests += 1
        return self.stopping


class SyncStopServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "archive"
        self.root.mkdir()
        self.engine = _Engine(stopping=True)
        self.server = ArchiveHTTPServer(
            ("127.0.0.1", 0),
            Handler,
            db=object(),
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
        *,
        authenticated: bool = True,
        origin: str | None = None,
    ) -> tuple[int, dict]:
        host, port = self.server.server_address
        connection = HTTPConnection(host, port, timeout=2)
        headers: dict[str, str] = {}
        if authenticated:
            headers["Cookie"] = f"{SESSION_COOKIE}=valid-session"
        if origin is not None:
            headers["Origin"] = origin
        connection.request("POST", "/api/sync/stop", body=b"", headers=headers)
        response = connection.getresponse()
        body = json.loads(response.read())
        status = response.status
        connection.close()
        return status, body

    def test_stop_requests_cancellation_for_an_active_sync(self) -> None:
        host, port = self.server.server_address

        status, body = self._request(origin=f"http://{host}:{port}")

        self.assertEqual(status, 202)
        self.assertEqual(
            body,
            {
                "stopping": True,
                "message": "Synchronization stop requested.",
            },
        )
        self.assertEqual(self.engine.stop_requests, 1)

    def test_stop_returns_conflict_when_no_sync_is_running(self) -> None:
        self.engine.stopping = False

        status, body = self._request()

        self.assertEqual(status, 409)
        self.assertEqual(
            body,
            {
                "stopping": False,
                "message": "No synchronization is running.",
            },
        )
        self.assertEqual(self.engine.stop_requests, 1)

    def test_stop_requires_authentication(self) -> None:
        status, body = self._request(authenticated=False)

        self.assertEqual(status, 401)
        self.assertEqual(body, {"error": "Authentication required."})
        self.assertEqual(self.engine.stop_requests, 0)

    def test_stop_rejects_cross_origin_requests(self) -> None:
        status, body = self._request(origin="https://attacker.invalid")

        self.assertEqual(status, 403)
        self.assertEqual(body, {"error": "Cross-origin request rejected."})
        self.assertEqual(self.engine.stop_requests, 0)


class HandlerLoggingTests(unittest.TestCase):
    def test_log_message_handles_a_missing_request_path(self) -> None:
        handler = object.__new__(Handler)
        handler.command = "GET"

        with patch("app.server.log.info") as info:
            Handler.log_message(handler, "%s", "GET", "400")

        info.assert_called_once_with("%s %s %s", "GET", "", "400")


if __name__ == "__main__":
    unittest.main()
