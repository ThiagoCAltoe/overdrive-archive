from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from app.server import ArchiveHTTPServer, Handler, SESSION_COOKIE


class _Auth:
    def validate_session(self, token: str) -> bool:
        return token == "valid-session"

    def options(self) -> dict:
        return {}


class _Database:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    def get_item(self, item_id: int) -> dict | None:
        return next(
            (dict(item) for item in self.items if item["id"] == item_id),
            None,
        )

    def list_items(self, **_filters) -> list[dict]:
        return [dict(item) for item in self.items]

    def recording_subtypes(self) -> list[dict]:
        return []


class ThumbnailServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "archive"
        self.root.mkdir()
        self.items = [
            {
                "id": 1,
                "category": "recordings",
                "subtype": "replay",
                "relative_path": "vehicles/test/clip.mp4",
                "metadata_json": json.dumps(
                    {
                        "archiveCameraLayout": "dashcam",
                        "privateValue": "must-not-leak",
                    }
                ),
            },
            {
                "id": 2,
                "category": "recordings",
                "subtype": "oem_dashcam",
                "relative_path": "vehicles/test/missing.mp4",
                "metadata_json": "{}",
            },
        ]
        self.database = _Database(self.items)
        self.server = ArchiveHTTPServer(
            ("127.0.0.1", 0),
            Handler,
            db=self.database,
            engine=object(),
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
        path: str,
        *,
        authenticated: bool = True,
        request_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = HTTPConnection(
            self.server.server_address[0],
            self.server.server_address[1],
            timeout=2,
        )
        headers = dict(request_headers or {})
        if authenticated:
            headers["Cookie"] = f"{SESSION_COOKIE}=valid-session"
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        result = (
            response.status,
            {name.lower(): value for name, value in response.getheaders()},
            body,
        )
        connection.close()
        return result

    def _write_thumbnail(self, relative: str, body: bytes = b"jpeg-data") -> Path:
        path = (self.root / relative).with_suffix(".jpg")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def test_thumbnail_requires_authentication(self) -> None:
        self._write_thumbnail(self.items[0]["relative_path"])

        status, headers, body = self._request(
            "/thumbnail/1",
            authenticated=False,
        )

        self.assertEqual(status, 401)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(
            json.loads(body),
            {"error": "Authentication required."},
        )

    def test_thumbnail_is_served_with_private_cache_headers(self) -> None:
        expected = b"\xff\xd8thumbnail-jpeg\xff\xd9"
        self._write_thumbnail(self.items[0]["relative_path"], expected)

        status, headers, body = self._request("/thumbnail/1")

        self.assertEqual(status, 200)
        self.assertEqual(body, expected)
        self.assertEqual(headers["content-type"], "image/jpeg")
        self.assertEqual(headers["cache-control"], "private, max-age=300")
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(headers["content-length"], str(len(expected)))

    def test_media_range_streaming_is_unchanged(self) -> None:
        video = self.root / self.items[0]["relative_path"]
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"0123456789")

        status, headers, body = self._request(
            "/media/1",
            request_headers={"Range": "bytes=2-5"},
        )

        self.assertEqual(status, 206)
        self.assertEqual(body, b"2345")
        self.assertEqual(headers["accept-ranges"], "bytes")
        self.assertEqual(headers["content-range"], "bytes 2-5/10")
        self.assertEqual(headers["content-length"], "4")

    def test_items_only_advertise_existing_safe_thumbnails(self) -> None:
        self._write_thumbnail(self.items[0]["relative_path"])

        status, _headers, body = self._request("/api/items")

        self.assertEqual(status, 200)
        payload = json.loads(body)
        urls = {item["id"]: item["thumbnail_url"] for item in payload["items"]}
        self.assertEqual(urls, {1: "/thumbnail/1", 2: None})
        layouts = {item["id"]: item["camera_layout"] for item in payload["items"]}
        self.assertEqual(layouts, {1: "dashcam", 2: "single"})
        self.assertTrue(
            all("metadata_json" not in item for item in payload["items"])
        )
        self.assertNotIn(b"must-not-leak", body)

    def test_missing_thumbnail_returns_not_found(self) -> None:
        status, _headers, body = self._request("/thumbnail/2")

        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "Thumbnail not found."})

    def test_traversal_and_symlink_escape_are_not_served_or_advertised(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (outside / "escaped.jpg").write_bytes(b"outside")

        traversal_item = {
            "id": 3,
            "category": "recordings",
            "relative_path": "../outside/escaped.mp4",
        }
        symlink_item = {
            "id": 4,
            "category": "recordings",
            "relative_path": "vehicles/test/linked.mp4",
        }
        self.items.extend((traversal_item, symlink_item))
        linked = (self.root / symlink_item["relative_path"]).with_suffix(".jpg")
        linked.parent.mkdir(parents=True, exist_ok=True)
        linked.symlink_to(outside / "escaped.jpg")

        for path in (
            "/thumbnail/3",
            "/thumbnail/4",
            "/thumbnail/../../outside/escaped.jpg",
        ):
            with self.subTest(path=path):
                status, _headers, _body = self._request(path)
                self.assertEqual(status, 404)

        status, _headers, body = self._request("/api/items")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        urls = {item["id"]: item["thumbnail_url"] for item in payload["items"]}
        self.assertIsNone(urls[3])
        self.assertIsNone(urls[4])


if __name__ == "__main__":
    unittest.main()
