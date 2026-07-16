from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import Database
from app.sync import (
    RunTotals,
    SyncEngine,
    recording_camera_layout,
    recording_subtype,
)


RECORDING_BYTES = b"0123456789"
RECORDING_DIGEST = hashlib.sha256(RECORDING_BYTES).hexdigest()
RECORDING_TIMESTAMP = 1_784_196_610_000


class FakeRecordingClient:
    def __init__(self, *, expected_size: int = len(RECORDING_BYTES)):
        self.expected_size = expected_size
        self.downloads = 0

    def iter_recordings(self, recording_types, severities):
        yield {
            "filename": "cam_20260716_101010.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": self.expected_size,
            "videoUrl": "/video/cam_20260716_101010.mp4",
        }

    def status(self):
        return {"network": {"type": "wifi", "ssid": "Garage"}}

    def download_to(self, path, destination, **kwargs):
        self.downloads += 1
        destination.write_bytes(RECORDING_BYTES)
        return len(RECORDING_BYTES), RECORDING_DIGEST

    @staticmethod
    def encoded_filename(filename):
        return filename


class SyncEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = Database(root / "data" / "archive.sqlite3")
        self.engine = SyncEngine(self.db, root / "archive")

    def test_configuration_redaction_removes_sensitive_and_location_fields(self) -> None:
        payload = {
            "success": True,
            "appearance": {
                "theme": "dark",
                "supportUrl": "https://user:password@example.invalid/private",
            },
            "recording": {
                "enabled": True,
                "codec": "h264",
                "password": "secret",
                "accessCode": "12345678",
                "auth": {"token": "secret"},
            },
            "vehicle": {
                "modelId": "generic-ev",
                "modelName": "https://user:password@example.invalid/private",
            },
            "mqtt": {"password": "secret", "host": "broker"},
            "homeAddress": "private",
            "nested": {"apiToken": "secret", "enabled": True},
        }
        redacted = self.engine._redact_configuration(payload)
        self.assertTrue(redacted["success"])
        self.assertEqual(redacted["appearance"], {"theme": "dark"})
        self.assertEqual(
            redacted["recording"],
            {"enabled": True, "codec": "h264"},
        )
        self.assertEqual(redacted["vehicle"], {"modelId": "generic-ev"})
        self.assertNotIn("mqtt", redacted)
        self.assertNotIn("homeAddress", redacted)
        self.assertNotIn("nested", redacted)
        serialized = str(redacted)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("12345678", serialized)
        self.assertNotIn("example.invalid", serialized)

    def test_snapshot_is_deduplicated_by_content_hash(self) -> None:
        settings = self.db.get_settings()
        totals = RunTotals()
        payload = {"success": True, "items": [{"id": 1}]}
        self.engine._archive_snapshot(
            settings,
            totals,
            "automations",
            payload,
        )
        self.engine._archive_snapshot(
            settings,
            totals,
            "automations",
            payload,
        )
        self.assertEqual(totals.items_added, 1)
        self.assertEqual(totals.items_skipped, 1)
        items = self.db.list_items(category="automations")
        self.assertEqual(len(items), 1)
        archived = self.engine.archive_root / items[0]["relative_path"]
        self.assertTrue(archived.is_file())

    def test_replay_prefers_the_new_api_type(self) -> None:
        self.assertEqual(
            recording_subtype(
                {"filename": "replay_20260716_143012.mp4", "type": "replay"},
                "replay_20260716_143012.mp4",
            ),
            "replay",
        )

    def test_replay_falls_back_to_the_pr_150_filename_on_old_builds(self) -> None:
        self.assertEqual(
            recording_subtype(
                {"filename": "replay_20260716_143012.mp4", "type": "normal"},
                "replay_20260716_143012.mp4",
            ),
            "replay",
        )
        self.assertEqual(
            recording_subtype(
                {"filename": "cam_20260716_143012.mp4", "type": "normal"},
                "cam_20260716_143012.mp4",
            ),
            "drive",
        )

    def test_future_overdrive_recording_type_is_preserved(self) -> None:
        self.assertEqual(
            recording_subtype(
                {"filename": "capture_20260716.mp4", "type": "driverMonitoring"},
                "capture_20260716.mp4",
            ),
            "driver_monitoring",
        )

    def test_recording_camera_layout_uses_clip_metadata_then_vehicle_fallback(self) -> None:
        settings = self.db.get_settings()
        settings["vehicle"]["recording_layout"] = "dashcam"
        settings["vehicle"]["surveillance_layout"] = "standard"
        self.assertEqual(
            recording_camera_layout(
                {"layout": "standard"},
                "drive",
                settings,
            ),
            "standard",
        )
        self.assertEqual(
            recording_camera_layout({}, "replay", settings),
            "dashcam",
        )
        self.assertEqual(
            recording_camera_layout(
                {},
                "surveillance",
                settings,
                {"layout": "dashcam"},
            ),
            "dashcam",
        )
        self.assertEqual(
            recording_camera_layout({}, "oem_dashcam", settings),
            "single",
        )

    def _recording_settings(self, name: str = "Family car") -> dict:
        return self.db.save_settings(
            {
                "vehicle": {
                    "name": name,
                    "base_url": "https://vehicle.example",
                    "device_token": "byd-stable-device-12345678",
                    "device_id": "byd-stable-device",
                },
                "schedule": {"only_wifi": False},
                "content": {
                    "categories": ["recordings"],
                    "recording_types": ["normal"],
                    "include_unknown_recording_types": False,
                    "include_thumbnails": False,
                    "include_event_timeline": False,
                },
            }
        )

    def test_missing_inventory_file_is_downloaded_again(self) -> None:
        settings = self._recording_settings()
        client = FakeRecordingClient()
        self.engine._collect_recordings(client, settings, RunTotals())
        item = self.db.list_items(category="recordings")[0]
        archived = self.engine.archive_root / item["relative_path"]
        archived.unlink()

        client.downloads = 0
        totals = RunTotals()
        self.engine._collect_recordings(client, settings, totals)

        self.assertEqual(client.downloads, 1)
        self.assertEqual(archived.read_bytes(), RECORDING_BYTES)
        self.assertEqual(len(self.db.list_items(category="recordings")), 1)
        self.assertEqual(totals.bytes_added, len(RECORDING_BYTES))

    def test_wrong_size_orphan_is_replaced_before_inventory(self) -> None:
        settings = self._recording_settings()
        first_client = FakeRecordingClient()
        self.engine._collect_recordings(first_client, settings, RunTotals())
        item = self.db.list_items(category="recordings")[0]
        archived = self.engine.archive_root / item["relative_path"]
        with self.db.connect() as conn:
            conn.execute("DELETE FROM archive_items")
        archived.write_bytes(b"bad")

        client = FakeRecordingClient()
        self.engine._collect_recordings(client, settings, RunTotals())

        stored = self.db.list_items(category="recordings")
        self.assertEqual(client.downloads, 1)
        self.assertEqual(archived.read_bytes(), RECORDING_BYTES)
        self.assertEqual(stored[0]["size_bytes"], len(RECORDING_BYTES))

    def test_vehicle_rename_does_not_duplicate_recording(self) -> None:
        client = FakeRecordingClient()
        self.engine._collect_recordings(
            client,
            self._recording_settings("Car A"),
            RunTotals(),
        )
        self.engine._collect_recordings(
            client,
            self._recording_settings("Car B"),
            RunTotals(),
        )

        self.assertEqual(client.downloads, 1)
        self.assertEqual(len(self.db.list_items(category="recordings")), 1)

    def test_status_device_identity_is_used_when_profile_import_is_disabled(self) -> None:
        settings = self._recording_settings("Car A")
        settings = self.db.save_settings(
            {
                "vehicle": {
                    "device_id": "",
                    "device_token": "12345678",
                    "auto_detect_profile": False,
                }
            }
        )

        class StatusRecordingClient(FakeRecordingClient):
            def status(self):
                return {
                    "deviceId": "byd-stable-device",
                    "network": {"type": "wifi"},
                }

        client = StatusRecordingClient()
        with patch.object(self.engine, "_client", return_value=client):
            self.engine.run_once("manual")
            self.db.save_settings(
                {
                    "vehicle": {
                        "name": "Car B",
                        "base_url": "https://new-vehicle-address.example",
                    }
                }
            )
            self.engine.run_once("manual")

        self.assertFalse(
            self.db.get_settings()["vehicle"]["device_id"],
            "auto profile import is disabled, so the status identity is in-memory only",
        )
        self.assertEqual(client.downloads, 1)
        self.assertEqual(len(self.db.list_items(category="recordings")), 1)

    def test_recording_size_metadata_change_keeps_one_source_identity(self) -> None:
        settings = self._recording_settings()
        first = FakeRecordingClient(expected_size=0)
        self.engine._collect_recordings(first, settings, RunTotals())
        second = FakeRecordingClient(expected_size=len(RECORDING_BYTES))
        self.engine._collect_recordings(second, settings, RunTotals())

        self.assertEqual(second.downloads, 0)
        self.assertEqual(len(self.db.list_items(category="recordings")), 1)

    def test_existing_recording_gets_a_missing_thumbnail_without_redownload(self) -> None:
        client = FakeRecordingClient()
        settings = self._recording_settings()
        self.engine._collect_recordings(client, settings, RunTotals())
        settings = self.db.save_settings(
            {"content": {"include_thumbnails": True}}
        )

        with patch.object(
            self.engine,
            "_ensure_recording_thumbnail",
        ) as ensure_thumbnail:
            self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloads, 1)
        ensure_thumbnail.assert_called_once()

    def test_existing_recording_camera_layout_is_backfilled_without_redownload(self) -> None:
        client = FakeRecordingClient()
        settings = self._recording_settings()
        self.engine._collect_recordings(client, settings, RunTotals())
        settings = self.db.save_settings(
            {"vehicle": {"recording_layout": "dashcam"}}
        )

        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloads, 1)
        item = self.db.get_item(
            self.db.list_items(category="recordings")[0]["id"]
        )
        metadata = json.loads(item["metadata_json"])
        self.assertEqual(metadata["archiveCameraLayout"], "dashcam")

    def test_local_thumbnail_generation_uses_a_private_verified_jpeg(self) -> None:
        video = self.engine.archive_root / "sample.mp4"
        destination = video.with_suffix(".jpg")
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"video")

        def fake_run(command, **kwargs):
            Path(command[-1]).write_bytes(b"\xff\xd8" + b"x" * 600)

        with (
            patch("app.sync.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("app.sync.subprocess.run", side_effect=fake_run) as run,
        ):
            generated = self.engine._generate_recording_thumbnail(
                video,
                destination,
            )

        self.assertTrue(generated)
        self.assertTrue(destination.is_file())
        self.assertEqual(destination.read_bytes()[:2], b"\xff\xd8")
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        command = run.call_args.args[0]
        self.assertIn("-threads", command)
        self.assertIn("scale=640:-2:force_original_aspect_ratio=decrease", command)

    def test_local_thumbnail_generation_is_optional_without_ffmpeg(self) -> None:
        video = self.engine.archive_root / "sample.mp4"
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"video")
        with patch("app.sync.shutil.which", return_value=None):
            generated = self.engine._generate_recording_thumbnail(
                video,
                video.with_suffix(".jpg"),
            )
        self.assertFalse(generated)

    def test_trip_collectors_use_fixed_explicit_range(self) -> None:
        class FakeTripClient:
            def __init__(self):
                self.calls = []

            def fetch_paginated(self, path, array_key, **kwargs):
                self.calls.append((path, array_key, dict(kwargs["extra_params"])))
                return {array_key: []}

            def get_json(self, path, **kwargs):
                return {"success": True}

        settings = self._recording_settings()
        client = FakeTripClient()
        self.engine._collect_trips(client, settings, RunTotals())
        self.engine._collect_telemetry(client, settings, RunTotals(), None)

        self.assertEqual(len(client.calls), 2)
        for path, array_key, params in client.calls:
            self.assertEqual(path, "/api/trips")
            self.assertEqual(array_key, "trips")
            self.assertEqual(params["from"], 1)
            self.assertGreater(params["to"], 1_700_000_000_000)
            self.assertNotIn("days", params)

    def test_daily_schedule_catches_up_and_policy_skip_retries_soon(self) -> None:
        daily = self.db.save_settings(
            {
                "schedule": {
                    "enabled": True,
                    "mode": "daily",
                    "daily_time": "02:00",
                    "timezone": "UTC",
                }
            }
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_runs(reason,status,started_at,finished_at,message)
                VALUES('schedule','success',?,?, '')
                """,
                (
                    "2026-07-15T02:00:00+00:00",
                    "2026-07-15T02:01:00+00:00",
                ),
            )
        now = datetime(2026, 7, 16, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(self.engine._next_run_at(daily, now), now)

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_runs(reason,status,started_at,finished_at,message)
                VALUES('schedule','skipped',?,?, 'waiting for Wi-Fi')
                """,
                (
                    "2026-07-16T03:00:00+00:00",
                    "2026-07-16T03:00:01+00:00",
                ),
            )
        retry = self.engine._next_run_at(
            daily,
            datetime(2026, 7, 16, 3, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(
            retry,
            datetime(2026, 7, 16, 3, 5, tzinfo=timezone.utc),
        )

    def test_sync_profile_refresh_preserves_manual_model_fields(self) -> None:
        settings = self.db.save_settings(
            {
                "vehicle": {
                    "name": "Family car",
                    "base_url": "https://vehicle.example",
                    "device_token": "byd-stable-device-12345678",
                    "model_id": "manual-id",
                    "model_name": "Manual model",
                    "color": "#ffffff",
                    "drive_side": "lhd",
                    "auto_detect_profile": True,
                },
                "schedule": {"only_wifi": False},
                "content": {"categories": []},
            }
        )

        class FakeProfileClient:
            def status(self):
                return {
                    "deviceId": "byd-stable-device",
                    "network": {"type": "wifi"},
                }

            def discover_vehicle_profile(self, status):
                return {
                    "device_id": "byd-stable-device",
                    "app_version": "2.0",
                    "locale": "en-US",
                    "distance_unit": "km",
                    "model_id": "detected-id",
                    "model_name": "Detected model",
                    "color": "#000000",
                    "drive_side": "rhd",
                }

        with patch.object(
            self.engine,
            "_client",
            return_value=FakeProfileClient(),
        ):
            result = self.engine.run_once("manual")

        self.assertEqual(result["status"], "success")
        vehicle = self.db.get_settings()["vehicle"]
        self.assertEqual(vehicle["device_id"], "byd-stable-device")
        self.assertEqual(vehicle["app_version"], "2.0")
        self.assertEqual(vehicle["locale"], "en-US")
        self.assertEqual(vehicle["distance_unit"], "km")
        self.assertEqual(vehicle["model_id"], settings["vehicle"]["model_id"])
        self.assertEqual(vehicle["model_name"], settings["vehicle"]["model_name"])
        self.assertEqual(vehicle["color"], settings["vehicle"]["color"])
        self.assertEqual(vehicle["drive_side"], settings["vehicle"]["drive_side"])


if __name__ == "__main__":
    unittest.main()
