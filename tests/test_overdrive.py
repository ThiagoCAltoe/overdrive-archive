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


class DownloadResponse(io.BytesIO):
    def __init__(self, body: bytes, *, status: int = 200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


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

    def test_download_reports_byte_progress_and_checks_policy_each_chunk(self) -> None:
        destination = Path(self.temp.name) / "recording.part"
        body = b"x" * (1024 * 1024 + 7)
        self.client._open = lambda path: DownloadResponse(body)
        policy_calls = []
        progress = []

        size, _digest = self.client.download_to(
            "/video/synthetic.mp4",
            destination,
            max_bytes=len(body),
            expected_size=len(body),
            policy_check=lambda: policy_calls.append(True),
            progress_callback=lambda done, total: progress.append((done, total)),
        )

        self.assertEqual(size, len(body))
        self.assertGreaterEqual(len(policy_calls), 4)
        self.assertEqual(progress[0], (0, len(body)))
        self.assertEqual(progress[-1], (len(body), len(body)))

    def test_interrupted_valid_download_keeps_a_resumable_part(self) -> None:
        destination = Path(self.temp.name) / "recording.mp4.part"
        body = b"x" * (2 * 1024 * 1024)
        self.client._open = lambda path: DownloadResponse(
            body,
            headers={"Content-Length": str(len(body)), "ETag": '"stable"'},
        )
        calls = 0

        def stop_after_first_chunk():
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("stop")

        with self.assertRaisesRegex(RuntimeError, "stop"):
            self.client.download_to(
                "/video/synthetic.mp4",
                destination,
                max_bytes=len(body),
                expected_size=len(body),
                source_identity="vehicle:recording:synthetic",
                resume=True,
                policy_check=stop_after_first_chunk,
            )

        self.assertEqual(destination.stat().st_size, 1024 * 1024)
        self.assertEqual(
            self.client.resumable_size(
                destination,
                source_identity="vehicle:recording:synthetic",
                expected_size=len(body),
            ),
            1024 * 1024,
        )

    def test_valid_part_resumes_with_range_and_hashes_the_complete_file(self) -> None:
        destination = Path(self.temp.name) / "recording.mp4.part"
        destination.write_bytes(b"abc")
        self.client._write_partial_metadata(
            self.client._partial_metadata_path(destination),
            source_identity="vehicle:recording:synthetic",
            expected_size=6,
            total_size=6,
            validator=("etag", '"stable"'),
        )
        requests = []

        def open_range(path, **kwargs):
            requests.append(kwargs)
            return DownloadResponse(
                b"def",
                status=206,
                headers={
                    "Content-Length": "3",
                    "Content-Range": "bytes 3-5/6",
                    "ETag": '"stable"',
                },
            )

        self.client._open = open_range
        size, digest = self.client.download_to(
            "/video/synthetic.mp4",
            destination,
            max_bytes=6,
            expected_size=6,
            source_identity="vehicle:recording:synthetic",
            resume=True,
        )

        self.assertEqual(requests[0]["request_headers"]["Range"], "bytes=3-")
        self.assertEqual(requests[0]["request_headers"]["If-Range"], '"stable"')
        self.assertEqual(destination.read_bytes(), b"abcdef")
        self.assertEqual(size, 6)
        self.assertEqual(digest, hashlib.sha256(b"abcdef").hexdigest())

    def test_unknown_expected_size_accepts_a_complete_valid_part(self) -> None:
        destination = Path(self.temp.name) / "recording.mp4.part"
        destination.write_bytes(b"abcdef")
        self.client._write_partial_metadata(
            self.client._partial_metadata_path(destination),
            source_identity="vehicle:recording:synthetic",
            expected_size=0,
            total_size=6,
            validator=("etag", '"stable"'),
        )
        self.client._open = Mock(
            side_effect=AssertionError("a complete part must not request Range at EOF")
        )
        progress = []

        size, digest = self.client.download_to(
            "/video/synthetic.mp4",
            destination,
            max_bytes=6,
            expected_size=0,
            source_identity="vehicle:recording:synthetic",
            resume=True,
            progress_callback=lambda done, total: progress.append((done, total)),
        )

        self.client._open.assert_not_called()
        self.assertEqual(progress, [(6, 6)])
        self.assertEqual(size, 6)
        self.assertEqual(digest, hashlib.sha256(b"abcdef").hexdigest())

    def test_resume_rejects_remote_total_above_reduced_limit_before_reading(self) -> None:
        class TrackingResponse(DownloadResponse):
            read_calls = 0

            def read(self, *args, **kwargs):
                self.read_calls += 1
                return super().read(*args, **kwargs)

        destination = Path(self.temp.name) / "recording.mp4.part"
        destination.write_bytes(b"abc")
        metadata = self.client._partial_metadata_path(destination)
        self.client._write_partial_metadata(
            metadata,
            source_identity="vehicle:recording:synthetic",
            expected_size=10,
            total_size=10,
            validator=("etag", '"stable"'),
        )
        response = TrackingResponse(
            b"defghij",
            status=206,
            headers={
                "Content-Length": "7",
                "Content-Range": "bytes 3-9/10",
                "ETag": '"stable"',
            },
        )
        self.client._open = lambda path, **kwargs: response

        with self.assertRaisesRegex(OverdriveError, "configured size limit"):
            self.client.download_to(
                "/video/synthetic.mp4",
                destination,
                max_bytes=5,
                expected_size=10,
                source_identity="vehicle:recording:synthetic",
                resume=True,
            )

        self.assertEqual(response.read_calls, 0)
        self.assertEqual(destination.read_bytes(), b"abc")
        self.assertTrue(metadata.exists())

    def test_full_response_after_range_restarts_instead_of_appending(self) -> None:
        destination = Path(self.temp.name) / "recording.mp4.part"
        destination.write_bytes(b"old")
        self.client._write_partial_metadata(
            self.client._partial_metadata_path(destination),
            source_identity="vehicle:recording:synthetic",
            expected_size=6,
            total_size=6,
            validator=("etag", '"old"'),
        )
        self.client._open = lambda path, **kwargs: DownloadResponse(
            b"UVWXYZ",
            status=200,
            headers={"Content-Length": "6", "ETag": '"new"'},
        )

        self.client.download_to(
            "/video/synthetic.mp4",
            destination,
            max_bytes=6,
            expected_size=6,
            source_identity="vehicle:recording:synthetic",
            resume=True,
        )

        self.assertEqual(destination.read_bytes(), b"UVWXYZ")

    def test_invalid_resume_range_discards_untrusted_partial(self) -> None:
        destination = Path(self.temp.name) / "recording.mp4.part"
        destination.write_bytes(b"abc")
        metadata = self.client._partial_metadata_path(destination)
        self.client._write_partial_metadata(
            metadata,
            source_identity="vehicle:recording:synthetic",
            expected_size=6,
            total_size=6,
            validator=("etag", '"stable"'),
        )
        self.client._open = lambda path, **kwargs: DownloadResponse(
            b"def",
            status=206,
            headers={
                "Content-Length": "3",
                "Content-Range": "bytes 2-4/6",
                "ETag": '"stable"',
            },
        )

        with self.assertRaisesRegex(OverdriveError, "invalid resumed"):
            self.client.download_to(
                "/video/synthetic.mp4",
                destination,
                max_bytes=6,
                expected_size=6,
                source_identity="vehicle:recording:synthetic",
                resume=True,
            )

        self.assertFalse(destination.exists())
        self.assertFalse(metadata.exists())

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

    def test_recording_listing_requires_complete_pagination_metadata(self) -> None:
        self.client.get_json = Mock(
            return_value={
                "recordings": [{"filename": "one.mp4"}],
                "totalCount": 201,
                "totalPages": 2,
                "page": 1,
                "pageSize": 200,
            }
        )

        with self.assertRaisesRegex(OverdriveError, "incomplete page"):
            list(self.client.iter_recordings([], []))

    def test_recording_listing_reads_every_declared_page(self) -> None:
        first_page = [
            {"filename": f"cam_{index:03d}.mp4"}
            for index in range(200)
        ]

        def listing(path, **_kwargs):
            if "page=1" in path:
                recordings = first_page
                page = 1
            else:
                recordings = [{"filename": "cam_200.mp4"}]
                page = 2
            return {
                "recordings": recordings,
                "totalCount": 201,
                "totalPages": 2,
                "page": page,
                "pageSize": 200,
            }

        self.client.get_json = Mock(side_effect=listing)

        recordings = list(self.client.iter_recordings([], []))

        self.assertEqual(len(recordings), 201)
        self.assertEqual(self.client.get_json.call_count, 2)

    def test_recording_listing_adopts_server_page_size_clamp(self) -> None:
        available = [
            {"filename": f"cam_{index:03d}.mp4"}
            for index in range(121)
        ]
        requested_page_sizes = []

        def clamped_listing(path, **_kwargs):
            query = path.partition("?")[2]
            params = dict(
                part.split("=", 1)
                for part in query.split("&")
            )
            page = int(params["page"])
            requested_page_size = int(params["pageSize"])
            requested_page_sizes.append(requested_page_size)
            page_size = min(requested_page_size, 50)
            start = (page - 1) * page_size
            total_pages = (len(available) + page_size - 1) // page_size
            return {
                "recordings": available[start : start + page_size],
                "totalCount": len(available),
                "totalPages": total_pages,
                "page": page,
                "pageSize": page_size,
            }

        self.client.get_json = Mock(side_effect=clamped_listing)

        recordings = list(self.client.iter_recordings([], []))

        self.assertEqual(recordings, available)
        self.assertEqual(requested_page_sizes, [200, 50, 50])

    def test_recording_listing_rejects_page_size_change_after_first_page(self) -> None:
        self.client.get_json = Mock(
            side_effect=[
                {
                    "recordings": [
                        {"filename": f"cam_{index:03d}.mp4"}
                        for index in range(50)
                    ],
                    "totalCount": 75,
                    "totalPages": 2,
                    "page": 1,
                    "pageSize": 50,
                },
                {
                    "recordings": [
                        {"filename": f"cam_{index:03d}.mp4"}
                        for index in range(50, 75)
                    ],
                    "totalCount": 75,
                    "totalPages": 3,
                    "page": 2,
                    "pageSize": 25,
                },
            ]
        )

        with self.assertRaisesRegex(OverdriveError, "inconsistent pagination"):
            list(self.client.iter_recordings([], []))

    def test_recording_listing_rejects_a_count_change_between_pages(self) -> None:
        first_page = [{"filename": f"cam_{index:03d}.mp4"} for index in range(200)]
        second_page = [{"filename": "cam_200.mp4"}, {"filename": "cam_201.mp4"}]
        self.client.get_json = Mock(
            side_effect=[
                {
                    "recordings": first_page,
                    "totalCount": 201,
                    "totalPages": 2,
                    "page": 1,
                    "pageSize": 200,
                },
                {
                    "recordings": second_page,
                    "totalCount": 202,
                    "totalPages": 2,
                    "page": 2,
                    "pageSize": 200,
                },
            ]
        )

        with self.assertRaisesRegex(OverdriveError, "changed while"):
            list(self.client.iter_recordings([], []))


if __name__ == "__main__":
    unittest.main()
