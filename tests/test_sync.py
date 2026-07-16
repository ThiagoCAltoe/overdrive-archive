from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import Database
from app.overdrive import OverdriveError
from app.sync import (
    RecordingQueueEntry,
    RunTotals,
    SyncEngine,
    recording_camera_layout,
    recording_queue_priority,
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


class QueueRecordingClient:
    def __init__(self, items, *, engine=None):
        self.items = list(items)
        self.engine = engine
        self.downloads = []
        self.progress_states = []
        self.discovery_complete = False
        self.append_on_first_download = None

    def iter_recordings(self, recording_types, severities):
        for item in self.items:
            yield dict(item)
        self.discovery_complete = True

    def status(self):
        return {"network": {"type": "wifi", "ssid": "Garage"}}

    def download_to(self, path, destination, **kwargs):
        if not self.discovery_complete:
            raise AssertionError("download began before the discovery snapshot finished")
        filename = Path(path).name
        self.downloads.append(filename)
        if self.append_on_first_download is not None and len(self.downloads) == 1:
            self.items.append(dict(self.append_on_first_download))
        size = int(kwargs.get("expected_size") or 1)
        progress = kwargs.get("progress_callback")
        if progress:
            progress(1, size)
            if self.engine is not None:
                self.progress_states.append(self.engine.state())
        raw = bytes([65 + len(self.downloads) % 20]) * size
        destination.write_bytes(raw)
        if progress:
            progress(size, size)
        return size, hashlib.sha256(raw).hexdigest()

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

    @staticmethod
    def _queue_entry(
        filename: str,
        *,
        timestamp: int,
        partial: int = 0,
        size: int = 100,
        known: bool = False,
    ) -> RecordingQueueEntry:
        path = Path("/tmp") / filename
        return RecordingQueueEntry(
            item={"filename": filename},
            source_key=f"source:{filename}",
            filename=filename,
            subtype="drive",
            timestamp_ms=timestamp,
            expected_size=size,
            relative=Path(filename),
            final_path=path,
            partial_path=path.with_suffix(path.suffix + ".part"),
            existing=None,
            needs_download=True,
            partial_size=partial,
            known_before_run=known,
        )

    def test_recording_queue_has_the_three_dashboard_priority_levels(self) -> None:
        entries = [
            self._queue_entry("new-oldest.mp4", timestamp=1, known=False),
            self._queue_entry("known-newer.mp4", timestamp=30, known=True),
            self._queue_entry("partial-large.mp4", timestamp=40, partial=10, size=100),
            self._queue_entry("partial-near.mp4", timestamp=50, partial=95, size=100),
            self._queue_entry("known-older.mp4", timestamp=20, known=True),
            self._queue_entry("new-newer.mp4", timestamp=10, known=False),
        ]

        ordered = sorted(entries, key=recording_queue_priority)

        self.assertEqual(
            [entry.filename for entry in ordered],
            [
                "partial-near.mp4",
                "partial-large.mp4",
                "known-older.mp4",
                "known-newer.mp4",
                "new-oldest.mp4",
                "new-newer.mp4",
            ],
        )

    def test_recording_queue_is_frozen_until_the_next_sync(self) -> None:
        settings = self._recording_settings()
        first = {
            "filename": "cam_20260716_100000.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 10,
            "videoUrl": "/video/cam_20260716_100000.mp4",
        }
        second = {
            "filename": "cam_20260716_101000.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP + 1,
            "size": 10,
            "videoUrl": "/video/cam_20260716_101000.mp4",
        }
        discovered_late = {
            "filename": "cam_20260716_102000.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP + 2,
            "size": 10,
            "videoUrl": "/video/cam_20260716_102000.mp4",
        }
        client = QueueRecordingClient([first, second])
        client.append_on_first_download = discovered_late

        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(
            client.downloads,
            [first["filename"], second["filename"]],
        )
        client.downloads = []
        client.append_on_first_download = None
        self.engine._collect_recordings(client, settings, RunTotals())
        self.assertEqual(client.downloads, [discovered_late["filename"]])

    def test_complete_listing_removes_a_backlog_job_missing_from_vehicle(self) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        missing_key = f"{identity}:recording:cam_missing.mp4:{RECORDING_TIMESTAMP}"
        self.db.remember_recording_download_jobs(
            identity,
            {
                missing_key: {
                    "filename": "cam_missing.mp4",
                    "type": "normal",
                    "timestamp": RECORDING_TIMESTAMP,
                    "size": 10,
                }
            },
        )

        client = QueueRecordingClient([])
        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(self.db.list_recording_download_jobs(identity), [])
        self.assertEqual(client.downloads, [])

    def test_failed_listing_never_reconciles_deleted_placeholders(self) -> None:
        settings = self._recording_settings()
        client = FakeRecordingClient()
        self.engine._collect_recordings(client, settings, RunTotals())
        listed = self.db.list_items(category="recordings")[0]
        archived = self.db.get_item(int(listed["id"]))
        path = self.engine.archive_root / archived["relative_path"]
        path.unlink()
        self.assertTrue(self.db.delete_archive_item(int(archived["id"])))

        class InterruptedListing(QueueRecordingClient):
            def iter_recordings(self, *_args):
                yield {
                    "filename": "cam_other.mp4",
                    "type": "normal",
                    "timestamp": RECORDING_TIMESTAMP + 1,
                    "size": 10,
                }
                raise OverdriveError("listing interrupted")

        with self.assertRaisesRegex(OverdriveError, "listing interrupted"):
            self.engine._collect_recordings(
                InterruptedListing([]),
                settings,
                RunTotals(),
            )

        self.assertTrue(self.db.is_retention_tombstoned(archived["source_key"]))

    def test_restore_sync_is_vehicle_scoped_and_bypasses_disabled_filters(self) -> None:
        settings = self._recording_settings()
        original_device_id = settings["vehicle"]["device_id"]
        original_token = settings["vehicle"]["device_token"]
        original_client = FakeRecordingClient()
        self.engine._collect_recordings(original_client, settings, RunTotals())
        listed = self.db.list_items(category="recordings")[0]
        archived = self.db.get_item(int(listed["id"]))
        (self.engine.archive_root / archived["relative_path"]).unlink()
        self.assertTrue(self.db.delete_archive_item(int(archived["id"])))
        self.assertTrue(self.db.request_recording_restore(archived["source_key"]))
        self.db.save_settings(
            {
                "vehicle": {"auto_detect_profile": False},
                "content": {
                    "categories": ["trips"],
                    "recording_types": ["replay"],
                }
            }
        )

        class RestoreClient(FakeRecordingClient):
            def fetch_paginated(self, _path, array_key, **_kwargs):
                return {array_key: []}

        self.db.save_settings(
            {
                "vehicle": {
                    "device_id": "different-vehicle",
                    "device_token": "different-vehicle-12345678",
                }
            }
        )
        other_vehicle_client = RestoreClient()
        with patch.object(self.engine, "_client", return_value=other_vehicle_client):
            other_result = self.engine.run_once("restore")

        self.assertEqual(other_result["status"], "success")
        self.assertEqual(other_vehicle_client.downloads, 0)
        self.assertTrue(self.db.recording_restore_requested(archived["source_key"]))

        self.db.save_settings(
            {
                "vehicle": {
                    "device_id": original_device_id,
                    "device_token": original_token,
                }
            }
        )
        restore_client = RestoreClient()
        with patch.object(self.engine, "_client", return_value=restore_client):
            result = self.engine.run_once("restore")

        self.assertEqual(result["status"], "success")
        self.assertEqual(restore_client.downloads, 1)
        restored = self.db.get_item_by_source_key(archived["source_key"])
        self.assertIsNotNone(restored)
        self.assertTrue(self.db.is_retention_protected(archived["source_key"]))

    def test_queue_progress_is_weighted_by_file_bytes(self) -> None:
        settings = self._recording_settings()
        item = {
            "filename": "cam_20260716_103000.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 10,
            "videoUrl": "/video/cam_20260716_103000.mp4",
        }
        client = QueueRecordingClient([item], engine=self.engine)

        self.engine._collect_recordings(client, settings, RunTotals())

        during_transfer = client.progress_states[0]
        self.assertEqual(during_transfer["queue_bytes_done"], 1)
        self.assertEqual(during_transfer["queue_bytes_total"], 10)
        self.assertEqual(
            during_transfer["queue_bytes_done"]
            / during_transfer["queue_bytes_total"],
            0.1,
        )
        self.assertEqual(during_transfer["queue_items_done"], 0)
        self.assertEqual(during_transfer["queue_items_total"], 1)

    def test_one_failed_recording_does_not_starve_the_rest_of_the_queue(self) -> None:
        settings = self._recording_settings()
        blocked = {
            "filename": "cam_20260716_090000.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 10,
        }
        available = {
            "filename": "cam_20260716_091000.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP + 1,
            "size": 10,
        }

        class PartiallyFailingClient(QueueRecordingClient):
            def download_to(self, path, destination, **kwargs):
                if Path(path).name == blocked["filename"]:
                    self.downloads.append(Path(path).name)
                    raise OverdriveError("unavailable for test")
                return super().download_to(path, destination, **kwargs)

        client = PartiallyFailingClient([blocked, available])

        with self.assertRaisesRegex(OverdriveError, "remain queued"):
            self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(
            client.downloads,
            [blocked["filename"], available["filename"]],
        )
        self.assertEqual(
            [item["filename"] for item in self.db.list_items(category="recordings")],
            [available["filename"]],
        )
        jobs = self.db.list_recording_download_jobs(
            self.engine._vehicle_identity(settings)
        )
        self.assertEqual([job["item"]["filename"] for job in jobs], [blocked["filename"]])

    def test_stop_is_cooperative_preserves_part_and_resets_for_next_run(self) -> None:
        settings = self._recording_settings()
        self.db.save_settings(
            {
                "vehicle": {"auto_detect_profile": False},
                "content": {"categories": ["recordings", "trips"]},
            }
        )
        started = threading.Event()

        class CancellableClient(FakeRecordingClient):
            def __init__(self):
                super().__init__(expected_size=10)
                self.calls = 0
                self.trip_calls = 0

            def download_to(self, path, destination, **kwargs):
                self.calls += 1
                if self.calls > 1:
                    return super().download_to(path, destination, **kwargs)
                destination.write_bytes(RECORDING_BYTES[:5])
                from app.overdrive import OverdriveClient

                OverdriveClient._write_partial_metadata(
                    OverdriveClient._partial_metadata_path(destination),
                    source_identity=kwargs["source_identity"],
                    expected_size=10,
                    total_size=10,
                    validator=("etag", '"stable"'),
                )
                started.set()
                while True:
                    kwargs["policy_check"]()
                    threading.Event().wait(0.01)

            def fetch_paginated(self, *args, **kwargs):
                self.trip_calls += 1
                return {"trips": []}

        client = CancellableClient()
        with patch.object(self.engine, "_client", return_value=client):
            self.assertTrue(self.engine.trigger("manual"))
            self.assertTrue(started.wait(2))
            self.assertFalse(self.engine.trigger("manual"))
            self.assertTrue(self.engine.request_stop())
            worker = self.engine._sync_thread
            self.assertIsNotNone(worker)
            worker.join(2)

            self.assertFalse(self.engine.state()["active"])
            run = self.db.list_runs(1)[0]
            self.assertEqual(run["status"], "cancelled")
            self.assertEqual(run["error_count"], 0)
            self.assertEqual(client.trip_calls, 0)
            partials = list(self.engine.archive_root.rglob("*.mp4.part"))
            self.assertEqual(len(partials), 1)
            self.assertEqual(partials[0].stat().st_size, 5)

            self.assertTrue(self.engine.trigger("manual"))
            worker = self.engine._sync_thread
            self.assertIsNotNone(worker)
            worker.join(2)

        self.assertEqual(self.db.list_runs(1)[0]["status"], "success")
        self.assertFalse(list(self.engine.archive_root.rglob("*.mp4.part")))
        self.assertEqual(len(self.db.list_items(category="recordings")), 1)

    def test_stop_returns_false_while_idle(self) -> None:
        self.assertFalse(self.engine.request_stop())

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
