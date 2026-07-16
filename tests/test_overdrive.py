from __future__ import annotations

import hashlib
import io
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError

from app.overdrive import OverdriveClient, OverdriveError


class OverdriveClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = OverdriveClient(
            base_url="https://vehicle.invalid",
            device_token="synthetic-token",
        )
        self.client._open = lambda path: io.BytesIO(b"archive-data")

    def test_download_creates_a_private_file_exclusively(self) -> None:
        destination = Path(self.temp.name) / "recording.part"
        size, digest = self.client.download_to(
            "/video/synthetic.mp4",
            destination,
            max_bytes=1024,
        )

        self.assertEqual(size, len(b"archive-data"))
        self.assertEqual(digest, hashlib.sha256(b"archive-data").hexdigest())
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def test_download_refuses_to_overwrite_an_existing_path(self) -> None:
        destination = Path(self.temp.name) / "recording.part"
        destination.write_bytes(b"keep-me")

        with self.assertRaises(OverdriveError):
            self.client.download_to(
                "/video/synthetic.mp4",
                destination,
                max_bytes=1024,
            )

        self.assertEqual(destination.read_bytes(), b"keep-me")

    def test_download_refuses_a_symlink_without_touching_its_target(self) -> None:
        target = Path(self.temp.name) / "outside"
        target.write_bytes(b"keep-me")
        destination = Path(self.temp.name) / "recording.part"
        destination.symlink_to(target)

        with self.assertRaises(OverdriveError):
            self.client.download_to(
                "/video/synthetic.mp4",
                destination,
                max_bytes=1024,
            )

        self.assertTrue(destination.is_symlink())
        self.assertEqual(target.read_bytes(), b"keep-me")

    def test_existing_bearer_jwt_is_used_without_token_exchange(self) -> None:
        bearer = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        client = OverdriveClient(
            base_url="https://vehicle.invalid",
            device_token=bearer,
        )
        client.get_json = Mock(
            side_effect=AssertionError("JWT must not use /auth/token")
        )

        client.authenticate()

        self.assertEqual(client.jwt, bearer)
        client.get_json.assert_not_called()

    def test_vehicle_http_error_body_is_not_exposed(self) -> None:
        client = OverdriveClient(
            base_url="https://vehicle.invalid",
            device_token="synthetic-token",
        )
        client.opener.open = Mock(
            side_effect=HTTPError(
                "https://vehicle.invalid/api/private",
                500,
                "synthetic failure",
                {},
                io.BytesIO(b'{"error":"private-token-and-location"}'),
            )
        )

        with self.assertRaises(OverdriveError) as raised:
            client._open("/api/private", authenticated=False)

        self.assertIn("HTTP 500", str(raised.exception))
        self.assertNotIn("private-token", str(raised.exception))

    def test_vehicle_profile_discovers_recording_layouts(self) -> None:
        client = OverdriveClient(
            base_url="https://vehicle.invalid",
            device_token="synthetic-token",
        )

        def fake_get_json(path, **_kwargs):
            responses = {
                "/api/models/selected": {},
                "/api/models/list": {"models": []},
                "/api/settings/recording-layout": {"layout": "dashcam"},
                "/api/settings/surveillance-layout": {"layout": "standard"},
            }
            return responses[path]

        client.get_json = Mock(side_effect=fake_get_json)
        profile = client.discover_vehicle_profile(
            {"deviceId": "vehicle", "appVersion": "1.0"}
        )

        self.assertEqual(profile["recording_layout"], "dashcam")
        self.assertEqual(profile["surveillance_layout"], "standard")


if __name__ == "__main__":
    unittest.main()
