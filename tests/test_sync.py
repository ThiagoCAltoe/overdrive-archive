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
from app.overdrive import OverdriveClient, OverdriveError
from app.sync import (
    RecordingQueueEntry,
    RunTotals,
    SyncCancelled,
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


class PayloadRecordingClient:
    def __init__(self, item, payload: bytes):
        self.item = dict(item)
        self.payload = payload
        self.downloads = 0

    def iter_recordings(self, recording_types, severities):
        yield dict(self.item)

    def download_to(self, path, destination, **kwargs):
        self.downloads += 1
        destination.write_bytes(self.payload)
        return len(self.payload), hashlib.sha256(self.payload).hexdigest()

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

    def test_vanished_job_cleans_partial_without_touching_valid_item(self) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        filename = "cam_vanished.mp4"
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        remote_item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 32 * 1024 * 1024,
        }
        date = datetime.fromtimestamp(RECORDING_TIMESTAMP / 1000, timezone.utc)
        relative = (
            Path(settings["destination"]["subdirectory"])
            / self.engine._vehicle_slug(settings)
            / "recordings"
            / "drive"
            / f"{date:%Y}"
            / f"{date:%m}"
            / f"{date:%d}"
            / filename
        )
        final_path = self.engine.archive_root / relative
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_bytes = b"already archived and still valid"
        final_path.write_bytes(final_bytes)
        self.assertTrue(
            self.db.add_item(
                source_key=source_key,
                category="recordings",
                subtype="drive",
                vehicle=self.engine._vehicle_slug(settings),
                filename=filename,
                relative_path=str(relative),
                media_type="video/mp4",
                size_bytes=len(final_bytes),
                sha256=hashlib.sha256(final_bytes).hexdigest(),
                source_timestamp=RECORDING_TIMESTAMP,
                metadata=remote_item,
            )
        )

        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: remote_item},
            {
                source_key: str(
                    partial_path.relative_to(self.engine.archive_root)
                )
            },
        )
        with partial_path.open("wb") as handle:
            handle.truncate(32 * 1024 * 1024)
        outside_target = Path(self.temp.name) / "outside-resume-metadata.json"
        outside_target.write_text("outside must survive", encoding="utf-8")
        metadata_path = partial_path.with_name(partial_path.name + ".meta")
        metadata_path.symlink_to(outside_target)

        renamed_settings = self._recording_settings("Renamed family car")
        client = QueueRecordingClient([])
        self.engine._collect_recordings(client, renamed_settings, RunTotals())

        self.assertFalse(partial_path.exists())
        self.assertFalse(metadata_path.exists())
        self.assertEqual(
            outside_target.read_text(encoding="utf-8"),
            "outside must survive",
        )
        self.assertEqual(final_path.read_bytes(), final_bytes)
        self.assertIsNotNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])
        self.assertEqual(client.downloads, [])

    def test_vanished_job_recovers_final_after_crash_before_inventory(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        filename = "cam_crash_after_rename.mp4"
        payload = b"complete-after-atomic-rename"
        item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        _name, _subtype, _timestamp, relative, final_path = (
            self.engine._recording_archive_path(
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {
                source_key: str(
                    partial_path.relative_to(self.engine.archive_root)
                )
            },
        )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(payload)

        totals = RunTotals()
        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, totals
        )

        inventoried = self.db.get_item_by_source_key(source_key)
        self.assertIsNotNone(inventoried)
        self.assertEqual(inventoried["relative_path"], str(relative))
        self.assertEqual(inventoried["size_bytes"], len(payload))
        self.assertEqual(
            inventoried["sha256"], hashlib.sha256(payload).hexdigest()
        )
        self.assertEqual(final_path.read_bytes(), payload)
        self.assertTrue(final_path.with_suffix(".metadata.json").is_file())
        self.assertEqual(totals.items_added, 1)
        self.assertEqual(totals.bytes_added, 0)
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])

    def test_vanished_job_promotes_verified_full_part_before_cleanup(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        filename = "cam_crash_before_rename.mp4"
        payload = b"complete-part-with-validated-metadata"
        item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 0,
        }
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        partial_relative = str(
            partial_path.relative_to(self.engine.archive_root)
        )
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {source_key: partial_relative},
        )
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.write_bytes(payload)
        OverdriveClient._write_partial_metadata(
            OverdriveClient._partial_metadata_path(partial_path),
            source_identity=source_key,
            expected_size=0,
            total_size=len(payload),
            validator=("etag", '"completed-version"'),
        )

        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, RunTotals()
        )

        inventoried = self.db.get_item_by_source_key(source_key)
        self.assertIsNotNone(inventoried)
        self.assertEqual(
            inventoried["sha256"], hashlib.sha256(payload).hexdigest()
        )
        self.assertEqual(final_path.read_bytes(), payload)
        self.assertFalse(partial_path.exists())
        self.assertFalse(
            OverdriveClient._partial_metadata_path(partial_path).exists()
        )
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])

    def test_vanished_full_part_without_transfer_metadata_is_preserved(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        filename = "cam_unverified_full_part.mp4"
        payload = b"same-length-bytes-are-not-proof"
        item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {
                source_key: str(
                    partial_path.relative_to(self.engine.archive_root)
                )
            },
        )
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.write_bytes(payload)

        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, RunTotals()
        )

        self.assertEqual(partial_path.read_bytes(), payload)
        self.assertFalse(final_path.exists())
        self.assertIsNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(
            [
                job["source_key"]
                for job in self.db.list_recording_download_jobs(identity)
            ],
            [source_key],
        )

    def test_valid_inventory_keeps_job_when_restore_finalization_fails(
        self,
    ) -> None:
        settings = self._recording_settings()
        self.engine._collect_recordings(
            FakeRecordingClient(), settings, RunTotals()
        )
        listed = self.db.list_items(category="recordings")[0]
        inventoried = self.db.get_item(int(listed["id"]))
        self.assertIsNotNone(inventoried)
        source_key = str(inventoried["source_key"])
        identity = self.engine._vehicle_identity(settings)
        partial_path = (
            self.engine.archive_root / inventoried["relative_path"]
        ).with_suffix(".mp4.part")
        partial_relative = str(
            partial_path.relative_to(self.engine.archive_root)
        )
        item = {
            "filename": inventoried["filename"],
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(RECORDING_BYTES),
        }
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {source_key: partial_relative},
        )
        stored = self.db.list_recording_download_jobs(identity)[0]

        with patch.object(
            self.db, "recording_restore_requested", return_value=True
        ), patch.object(
            self.db, "complete_recording_restore", return_value=False
        ):
            recovered = self.engine._recover_vanished_recording(
                QueueRecordingClient([]),
                settings,
                settings["content"],
                RunTotals(),
                identity=identity,
                vehicle=self.engine._vehicle_slug(settings),
                stored=stored,
                partial_relative_path=partial_relative,
                policy_check=lambda: None,
            )

        self.assertFalse(recovered)
        self.assertEqual(
            [
                job["source_key"]
                for job in self.db.list_recording_download_jobs(identity)
            ],
            [source_key],
        )
        self.assertIsNotNone(self.db.get_item_by_source_key(source_key))

    def test_stop_during_vanished_recovery_keeps_final_and_job(self) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        filename = "cam_cancelled_recovery.mp4"
        payload = b"complete-but-recovery-was-stopped"
        item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {
                source_key: str(
                    partial_path.relative_to(self.engine.archive_root)
                )
            },
        )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(payload)

        with patch.object(
            self.engine,
            "_hash_file",
            side_effect=SyncCancelled("stopped during recovery"),
        ):
            with self.assertRaisesRegex(SyncCancelled, "stopped during recovery"):
                self.engine._collect_recordings(
                    QueueRecordingClient([]), settings, RunTotals()
                )

        self.assertEqual(final_path.read_bytes(), payload)
        self.assertIsNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(
            [
                job["source_key"]
                for job in self.db.list_recording_download_jobs(identity)
            ],
            [source_key],
        )

    def test_vanished_recovery_retries_after_metadata_sidecar_failure(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        filename = "cam_sidecar_retry.mp4"
        payload = b"complete-before-sidecar-failure"
        item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {
                source_key: str(
                    partial_path.relative_to(self.engine.archive_root)
                )
            },
        )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(payload)

        with patch.object(
            self.engine,
            "_write_json",
            side_effect=OSError("sidecar unavailable for test"),
        ):
            self.engine._collect_recordings(
                QueueRecordingClient([]), settings, RunTotals()
            )

        self.assertEqual(final_path.read_bytes(), payload)
        self.assertIsNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(len(self.db.list_recording_download_jobs(identity)), 1)

        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, RunTotals()
        )

        self.assertIsNotNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(final_path.read_bytes(), payload)
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])

    def test_unknown_size_sidecar_crash_recovers_from_completion_proof(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        filename = "cam_unknown_size_proof.mp4"
        item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 0,
        }
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        completion_path = self.engine._recording_completion_path(partial_path)
        client = QueueRecordingClient([item])
        original_write_json = self.engine._write_json

        def fail_archive_metadata(destination, payload):
            if destination.name.endswith(".metadata.json"):
                raise OSError("metadata sidecar crash for test")
            return original_write_json(destination, payload)

        first_totals = RunTotals()
        with patch.object(
            self.engine,
            "_write_json",
            side_effect=fail_archive_metadata,
        ):
            with self.assertRaisesRegex(OverdriveError, "remain queued"):
                self.engine._collect_recordings(
                    client, settings, first_totals
                )

        self.assertTrue(final_path.is_file())
        self.assertTrue(completion_path.is_file())
        self.assertIsNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(first_totals.bytes_added, 1)
        self.assertEqual(len(self.db.list_recording_download_jobs(identity)), 1)

        client.items = []
        recovery_totals = RunTotals()
        self.engine._collect_recordings(client, settings, recovery_totals)

        inventoried = self.db.get_item_by_source_key(source_key)
        self.assertIsNotNone(inventoried)
        self.assertEqual(inventoried["size_bytes"], 1)
        self.assertEqual(inventoried["sha256"], hashlib.sha256(b"B").hexdigest())
        self.assertEqual(recovery_totals.bytes_added, 0)
        self.assertFalse(completion_path.exists())
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])

    def test_vanished_final_with_wrong_completion_digest_is_preserved(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        filename = "cam_wrong_completion_digest.mp4"
        payload = b"complete-file-that-must-not-be-misidentified"
        item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {
                source_key: str(
                    partial_path.relative_to(self.engine.archive_root)
                )
            },
        )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(payload)
        self.engine._write_json(
            self.engine._recording_completion_path(partial_path),
            {
                "version": 1,
                "source_identity": source_key,
                "size": len(payload),
                "sha256": "0" * 64,
            },
        )

        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, RunTotals()
        )

        self.assertEqual(final_path.read_bytes(), payload)
        self.assertIsNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(len(self.db.list_recording_download_jobs(identity)), 1)
        self.assertTrue(
            self.engine._recording_completion_path(partial_path).is_file()
        )

    def test_vanished_job_uses_effective_inventory_path_after_vehicle_rename(
        self,
    ) -> None:
        original_settings = self._recording_settings("Original family car")
        initial_client = FakeRecordingClient()
        self.engine._collect_recordings(
            initial_client, original_settings, RunTotals()
        )
        archived = self.db.list_items(category="recordings")[0]
        final_path = self.engine.archive_root / archived["relative_path"]
        final_path.unlink()

        renamed_settings = self._recording_settings("Renamed family car")

        class InterruptedClient(FakeRecordingClient):
            def download_to(self, _path, destination, **_kwargs):
                destination.write_bytes(b"partial")
                raise OverdriveError("interrupted after partial for test")

        with self.assertRaisesRegex(OverdriveError, "remain queued"):
            self.engine._collect_recordings(
                InterruptedClient(), renamed_settings, RunTotals()
            )

        identity = self.engine._vehicle_identity(renamed_settings)
        jobs = self.db.list_recording_download_jobs(identity)
        self.assertEqual(len(jobs), 1)
        effective_partial = final_path.with_suffix(final_path.suffix + ".part")
        self.assertEqual(
            jobs[0]["partial_relative_path"],
            str(effective_partial.relative_to(self.engine.archive_root)),
        )
        self.assertTrue(effective_partial.exists())

        self.engine._collect_recordings(
            QueueRecordingClient([]), renamed_settings, RunTotals()
        )

        self.assertFalse(effective_partial.exists())
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])

    def test_vanished_job_preserves_partial_owned_by_effective_live_job(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        filename = "cam_effective_partial.mp4"
        vanished = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 32,
        }
        live = {
            **vanished,
            "timestamp": RECORDING_TIMESTAMP + 1_000,
        }
        vanished_key = (
            f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        )
        live_key = (
            f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP + 1_000}"
        )
        shared_partial = (
            self.engine.archive_root
            / settings["destination"]["subdirectory"]
            / self.engine._vehicle_slug(settings)
            / "recordings"
            / "drive"
            / "legacy"
            / f"{filename}.part"
        )
        shared_relative = str(
            shared_partial.relative_to(self.engine.archive_root)
        )
        self.db.remember_recording_download_jobs(
            identity,
            {vanished_key: vanished, live_key: live},
            {vanished_key: shared_relative, live_key: shared_relative},
        )
        shared_partial.parent.mkdir(parents=True, exist_ok=True)
        shared_partial.write_bytes(b"live resumable prefix")

        class InterruptedLiveClient(QueueRecordingClient):
            def download_to(self, path, destination, **kwargs):
                self.asserted_partial_exists = destination.exists()
                raise OverdriveError("interrupted for ownership test")

        client = InterruptedLiveClient([live])
        with self.assertRaisesRegex(OverdriveError, "remain queued"):
            self.engine._collect_recordings(client, settings, RunTotals())

        self.assertFalse(
            client.asserted_partial_exists,
            "an ambiguous live job must be rerouted before download",
        )

        # The ownership conflict must remain durable after the live job moves
        # to its unique path, or the next run could delete the legacy bytes.
        second_client = InterruptedLiveClient([live])
        with self.assertRaisesRegex(OverdriveError, "remain queued"):
            self.engine._collect_recordings(
                second_client, settings, RunTotals()
            )

        self.assertEqual(shared_partial.read_bytes(), b"live resumable prefix")
        self.assertEqual(
            {
                job["source_key"]
                for job in self.db.list_recording_download_jobs(identity)
            },
            {vanished_key, live_key},
        )

    def test_live_completion_proof_is_recovered_before_video_get(self) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        payload = b"complete-live-before-get"
        item = {
            "filename": "cam_live_proof.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        source_key = (
            f"{identity}:recording:{item['filename']}:{RECORDING_TIMESTAMP}"
        )
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings, item, identity=identity, vehicle=vehicle
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.write_bytes(payload)
        self.engine._write_recording_completion_proof(
            partial_path,
            source_key=source_key,
            size=len(payload),
            digest=hashlib.sha256(payload).hexdigest(),
        )
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {source_key: str(partial_path.relative_to(self.engine.archive_root))},
        )

        class NoVideoGetClient(QueueRecordingClient):
            def download_to(self, *_args, **_kwargs):
                raise AssertionError("completed live recording performed a GET")

        self.engine._collect_recordings(
            NoVideoGetClient([item]), settings, RunTotals()
        )

        archived = self.db.get_item_by_source_key(source_key)
        self.assertIsNotNone(archived)
        self.assertEqual(final_path.read_bytes(), payload)
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])

    def test_live_completion_proof_with_invalid_meta_never_retries_get(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        payload = b"valid-proof-invalid-meta"
        item = {
            "filename": "cam_live_invalid_meta.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        source_key = (
            f"{identity}:recording:{item['filename']}:{RECORDING_TIMESTAMP}"
        )
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings, item, identity=identity, vehicle=vehicle
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.write_bytes(payload)
        self.engine._write_recording_completion_proof(
            partial_path,
            source_key=source_key,
            size=len(payload),
            digest=hashlib.sha256(payload).hexdigest(),
        )
        metadata_path = OverdriveClient._partial_metadata_path(partial_path)
        metadata_path.write_text("{invalid-json", encoding="utf-8")
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {source_key: str(partial_path.relative_to(self.engine.archive_root))},
        )

        client = QueueRecordingClient([item])
        self.engine._collect_recordings(client, settings, RunTotals())
        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloads, [])
        self.assertEqual(partial_path.read_bytes(), payload)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), "{invalid-json")
        self.assertTrue(self.engine._recording_completion_path(partial_path).is_file())
        self.assertTrue(self.engine._recording_conflict_path(partial_path).is_file())
        self.assertIsNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(
            {job["source_key"] for job in self.db.list_recording_download_jobs(identity)},
            {source_key},
        )

    def test_live_completion_proof_with_other_source_meta_never_retries_get(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        payload = b"valid-proof-other-owner-meta"
        item = {
            "filename": "cam_live_other_owner_meta.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        source_key = (
            f"{identity}:recording:{item['filename']}:{RECORDING_TIMESTAMP}"
        )
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings, item, identity=identity, vehicle=vehicle
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.write_bytes(payload)
        self.engine._write_recording_completion_proof(
            partial_path,
            source_key=source_key,
            size=len(payload),
            digest=hashlib.sha256(payload).hexdigest(),
        )
        metadata_path = OverdriveClient._partial_metadata_path(partial_path)
        OverdriveClient._write_partial_metadata(
            metadata_path,
            source_identity=f"{identity}:recording:another-source:1",
            expected_size=len(payload),
            total_size=len(payload),
            validator=("etag", '"other-owner"'),
        )
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {source_key: str(partial_path.relative_to(self.engine.archive_root))},
        )

        client = QueueRecordingClient([item])
        self.engine._collect_recordings(client, settings, RunTotals())
        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloads, [])
        self.assertEqual(partial_path.read_bytes(), payload)
        self.assertTrue(metadata_path.is_file())
        self.assertTrue(self.engine._recording_completion_path(partial_path).is_file())
        self.assertTrue(self.engine._recording_conflict_path(partial_path).is_file())
        self.assertIsNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(
            {job["source_key"] for job in self.db.list_recording_download_jobs(identity)},
            {source_key},
        )

    def test_live_final_and_part_wait_for_concordant_meta_before_cleanup(
        self,
    ) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        final_payload = b"completed-final-with-second-part"
        partial_payload = b"resume-prefix"
        item = {
            "filename": "cam_live_final_and_part.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(final_payload),
        }
        source_key = (
            f"{identity}:recording:{item['filename']}:{RECORDING_TIMESTAMP}"
        )
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings, item, identity=identity, vehicle=vehicle
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(final_payload)
        partial_path.write_bytes(partial_payload)
        self.engine._write_recording_completion_proof(
            partial_path,
            source_key=source_key,
            size=len(final_payload),
            digest=hashlib.sha256(final_payload).hexdigest(),
        )
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {source_key: str(partial_path.relative_to(self.engine.archive_root))},
        )

        client = QueueRecordingClient([item])
        self.engine._collect_recordings(client, settings, RunTotals())
        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloads, [])
        self.assertEqual(final_path.read_bytes(), final_payload)
        self.assertEqual(partial_path.read_bytes(), partial_payload)
        self.assertTrue(self.engine._recording_completion_path(partial_path).is_file())
        self.assertTrue(self.engine._recording_conflict_path(partial_path).is_file())
        self.assertIsNone(self.db.get_item_by_source_key(source_key))

        metadata_path = OverdriveClient._partial_metadata_path(partial_path)
        OverdriveClient._write_partial_metadata(
            metadata_path,
            source_identity=source_key,
            expected_size=len(final_payload),
            total_size=len(final_payload),
            validator=("etag", '"same-owner"'),
        )
        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloads, [])
        self.assertEqual(final_path.read_bytes(), final_payload)
        self.assertIsNotNone(self.db.get_item_by_source_key(source_key))
        self.assertFalse(partial_path.exists())
        self.assertFalse(metadata_path.exists())
        self.assertFalse(self.engine._recording_completion_path(partial_path).exists())
        self.assertFalse(self.engine._recording_conflict_path(partial_path).exists())
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])

    def test_live_final_and_part_with_meta_only_remain_in_conflict(self) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        vehicle = self.engine._vehicle_slug(settings)
        final_payload = b"unproven-final-with-second-part"
        partial_payload = b"source-bound-prefix"
        item = {
            "filename": "cam_live_meta_only_conflict.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(final_payload),
        }
        source_key = (
            f"{identity}:recording:{item['filename']}:{RECORDING_TIMESTAMP}"
        )
        _name, _subtype, _timestamp, _relative, final_path = (
            self.engine._recording_archive_path(
                settings, item, identity=identity, vehicle=vehicle
            )
        )
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(final_payload)
        partial_path.write_bytes(partial_payload)
        metadata_path = OverdriveClient._partial_metadata_path(partial_path)
        OverdriveClient._write_partial_metadata(
            metadata_path,
            source_identity=source_key,
            expected_size=len(final_payload),
            total_size=len(final_payload),
            validator=("etag", '"meta-only"'),
        )
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: item},
            {source_key: str(partial_path.relative_to(self.engine.archive_root))},
        )

        client = QueueRecordingClient([item])
        self.engine._collect_recordings(client, settings, RunTotals())
        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloads, [])
        self.assertEqual(final_path.read_bytes(), final_payload)
        self.assertEqual(partial_path.read_bytes(), partial_payload)
        self.assertTrue(metadata_path.is_file())
        self.assertTrue(self.engine._recording_conflict_path(partial_path).is_file())
        self.assertIsNone(self.db.get_item_by_source_key(source_key))
        self.assertEqual(
            {job["source_key"] for job in self.db.list_recording_download_jobs(identity)},
            {source_key},
        )

    def test_shared_live_and_vanished_path_honors_each_proven_owner(self) -> None:
        for owner_kind in ("live", "vanished"):
            with self.subTest(owner=owner_kind):
                with tempfile.TemporaryDirectory() as directory:
                    db = Database(Path(directory) / "data" / "archive.sqlite3")
                    engine = SyncEngine(db, Path(directory) / "archive")
                    settings = db.save_settings(self._recording_settings())
                    identity = engine._vehicle_identity(settings)
                    filename = f"cam_shared_{owner_kind}.mp4"
                    payload = f"owner-{owner_kind}".encode()
                    vanished = {
                        "filename": filename,
                        "type": "normal",
                        "timestamp": RECORDING_TIMESTAMP,
                        "size": len(payload),
                    }
                    live = {
                        **vanished,
                        "timestamp": RECORDING_TIMESTAMP + 1_000,
                    }
                    vanished_key = (
                        f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
                    )
                    live_key = (
                        f"{identity}:recording:{filename}:"
                        f"{RECORDING_TIMESTAMP + 1_000}"
                    )
                    shared = (
                        engine.archive_root / "vehicles" / "legacy" / f"{filename}.part"
                    )
                    shared.parent.mkdir(parents=True, exist_ok=True)
                    shared.write_bytes(payload)
                    owner_key = live_key if owner_kind == "live" else vanished_key
                    engine._write_recording_completion_proof(
                        shared,
                        source_key=owner_key,
                        size=len(payload),
                        digest=hashlib.sha256(payload).hexdigest(),
                    )
                    shared_relative = str(shared.relative_to(engine.archive_root))
                    db.remember_recording_download_jobs(
                        identity,
                        {vanished_key: vanished, live_key: live},
                        {vanished_key: shared_relative, live_key: shared_relative},
                    )

                    client = QueueRecordingClient([live])
                    engine._collect_recordings(client, settings, RunTotals())

                    self.assertIsNotNone(db.get_item_by_source_key(owner_key))
                    self.assertEqual(db.list_recording_download_jobs(identity), [])
                    if owner_kind == "live":
                        self.assertEqual(client.downloads, [])
                    else:
                        self.assertEqual(client.downloads, [filename])
                        self.assertIsNotNone(db.get_item_by_source_key(live_key))

    def test_two_vanished_shared_jobs_recover_sidecar_owner_not_first_job(self) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        filename = "cam_two_vanished.mp4"
        payload = b"second-vanished-owner"
        first = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(payload),
        }
        second = {**first, "timestamp": RECORDING_TIMESTAMP + 1_000}
        first_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        second_key = (
            f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP + 1_000}"
        )
        shared = self.engine.archive_root / "vehicles" / "legacy" / f"{filename}.part"
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_bytes(payload)
        self.engine._write_recording_completion_proof(
            shared,
            source_key=second_key,
            size=len(payload),
            digest=hashlib.sha256(payload).hexdigest(),
        )
        shared_relative = str(shared.relative_to(self.engine.archive_root))
        self.db.remember_recording_download_jobs(
            identity,
            {first_key: first, second_key: second},
            {first_key: shared_relative, second_key: shared_relative},
        )

        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, RunTotals()
        )

        self.assertIsNone(self.db.get_item_by_source_key(first_key))
        self.assertIsNotNone(self.db.get_item_by_source_key(second_key))
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])

    def test_ambiguous_shared_vanished_path_preserves_bytes_and_jobs(self) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        filename = "cam_ambiguous_shared.mp4"
        first = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 32,
        }
        second = {**first, "timestamp": RECORDING_TIMESTAMP + 1_000}
        first_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        second_key = (
            f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP + 1_000}"
        )
        shared = self.engine.archive_root / "vehicles" / "legacy" / f"{filename}.part"
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_bytes(b"ambiguous-prefix")
        shared_relative = str(shared.relative_to(self.engine.archive_root))
        self.db.remember_recording_download_jobs(
            identity,
            {first_key: first, second_key: second},
            {first_key: shared_relative, second_key: shared_relative},
        )

        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, RunTotals()
        )

        # The conservative ownership decision must survive another discovery;
        # otherwise the second run could silently clean the same legacy bytes.
        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, RunTotals()
        )

        self.assertEqual(shared.read_bytes(), b"ambiguous-prefix")
        self.assertEqual(
            {job["source_key"] for job in self.db.list_recording_download_jobs(identity)},
            {first_key, second_key},
        )
        self.assertIsNone(self.db.get_item_by_source_key(first_key))
        self.assertIsNone(self.db.get_item_by_source_key(second_key))

    def test_missing_restore_cleans_partial_after_tombstone_reconciliation(
        self,
    ) -> None:
        settings = self._recording_settings()
        initial_client = FakeRecordingClient()
        self.engine._collect_recordings(initial_client, settings, RunTotals())
        listed = self.db.list_items(category="recordings")[0]
        archived = self.db.get_item(int(listed["id"]))
        self.assertIsNotNone(archived)
        source_key = str(archived["source_key"])
        final_path = self.engine.archive_root / archived["relative_path"]
        final_path.unlink()
        self.assertTrue(self.db.delete_archive_item(int(archived["id"])))
        self.assertTrue(self.db.request_recording_restore(source_key))

        remote_item = {
            "filename": archived["filename"],
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 32 * 1024 * 1024,
        }
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        identity = self.engine._vehicle_identity(settings)
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: remote_item},
            {
                source_key: str(
                    partial_path.relative_to(self.engine.archive_root)
                )
            },
        )
        partial_path.write_bytes(b"interrupted restore")
        metadata_path = partial_path.with_name(partial_path.name + ".meta")
        metadata_path.write_text('{"version":1}', encoding="utf-8")

        self.engine._collect_recordings(
            QueueRecordingClient([]), settings, RunTotals()
        )

        self.assertFalse(self.db.is_retention_tombstoned(source_key))
        self.assertFalse(self.db.recording_restore_requested(source_key))
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])
        self.assertFalse(partial_path.exists())
        self.assertFalse(metadata_path.exists())

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

        self.assertEqual(other_result["status"], "skipped")
        self.assertIn("another vehicle", other_result["message"])
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

    def test_failed_restore_finalization_keeps_job_for_safe_retry(self) -> None:
        settings = self._recording_settings()
        self.engine._collect_recordings(
            FakeRecordingClient(), settings, RunTotals()
        )
        listed = self.db.list_items(category="recordings")[0]
        archived = self.db.get_item(int(listed["id"]))
        self.assertIsNotNone(archived)
        source_key = str(archived["source_key"])
        (self.engine.archive_root / archived["relative_path"]).unlink()
        self.assertTrue(self.db.delete_archive_item(int(archived["id"])))
        self.assertTrue(self.db.request_recording_restore(source_key))

        with patch.object(
            self.db,
            "complete_recording_restore",
            return_value=False,
        ):
            with self.assertRaisesRegex(
                OverdriveError,
                "safely finalize",
            ):
                self.engine._collect_recordings(
                    FakeRecordingClient(), settings, RunTotals()
                )

        identity = self.engine._vehicle_identity(settings)
        self.assertEqual(len(self.db.list_recording_download_jobs(identity)), 1)
        self.assertTrue(self.db.recording_restore_requested(source_key))
        self.assertFalse(self.db.is_retention_protected(source_key))

        retry_client = FakeRecordingClient()
        self.engine._collect_recordings(retry_client, settings, RunTotals())

        self.assertEqual(retry_client.downloads, 0)
        self.assertEqual(self.db.list_recording_download_jobs(identity), [])
        self.assertFalse(self.db.is_retention_tombstoned(source_key))
        self.assertTrue(self.db.is_retention_protected(source_key))

    def test_restore_waits_for_pending_retention_cleanup(self) -> None:
        settings = self._recording_settings()
        self.engine._collect_recordings(
            FakeRecordingClient(), settings, RunTotals()
        )
        listed = self.db.list_items(category="recordings")[0]
        archived = self.db.get_item(int(listed["id"]))
        self.assertIsNotNone(archived)
        source_key = str(archived["source_key"])
        final_path = self.engine.archive_root / archived["relative_path"]
        final_path.unlink()
        self.assertTrue(self.db.delete_archive_item(int(archived["id"])))
        self.assertTrue(self.db.request_recording_restore(source_key))

        remote_item = {
            "filename": archived["filename"],
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(RECORDING_BYTES),
            "videoUrl": f"/video/{archived['filename']}",
        }
        identity = self.engine._vehicle_identity(settings)
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        self.db.remember_recording_download_jobs(
            identity,
            {source_key: remote_item},
            {
                source_key: str(
                    partial_path.relative_to(self.engine.archive_root)
                )
            },
        )
        partial_path.write_bytes(b"restore partial")
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO archive_retention_deletion_jobs(
                    item_id,source_key,category,original_relative_path,
                    staged_relative_path,prepared_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    999,
                    source_key,
                    "recordings",
                    archived["relative_path"],
                    str(
                        final_path.with_name(
                            ".retention-999-test.pending"
                        ).relative_to(self.engine.archive_root)
                    ),
                    "2026-07-16T17:30:00+00:00",
                ),
            )

        client = QueueRecordingClient([remote_item])
        self.engine._collect_recordings(client, settings, RunTotals())

        self.assertEqual(client.downloads, [])
        self.assertTrue(partial_path.exists())
        self.assertEqual(len(self.db.list_recording_download_jobs(identity)), 1)
        self.assertTrue(self.db.recording_restore_requested(source_key))
        self.assertTrue(
            self.db.recording_retention_cleanup_pending(source_key)
        )

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

    def test_corrected_timestamp_same_day_gets_an_independent_archive_path(
        self,
    ) -> None:
        settings = self._recording_settings()
        filename = "cam_corrected_timestamp.mp4"
        first_payload = b"first-version"
        second_payload = b"second-value!"
        first_item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(first_payload),
        }
        second_item = {
            **first_item,
            "timestamp": RECORDING_TIMESTAMP + 1_000,
            "size": len(second_payload),
        }
        first_client = PayloadRecordingClient(first_item, first_payload)
        second_client = PayloadRecordingClient(second_item, second_payload)

        self.engine._collect_recordings(first_client, settings, RunTotals())
        self.engine._collect_recordings(second_client, settings, RunTotals())

        archived = self.db.list_items(category="recordings")
        self.assertEqual(first_client.downloads, 1)
        self.assertEqual(second_client.downloads, 1)
        self.assertEqual(len(archived), 2)
        self.assertEqual(len({item["relative_path"] for item in archived}), 2)
        payloads = {
            int(item["source_timestamp"]): (
                self.engine.archive_root / item["relative_path"]
            ).read_bytes()
            for item in archived
        }
        self.assertEqual(payloads[RECORDING_TIMESTAMP], first_payload)
        self.assertEqual(payloads[RECORDING_TIMESTAMP + 1_000], second_payload)

    def test_different_vehicle_identity_with_same_slug_cannot_share_a_path(
        self,
    ) -> None:
        first_settings = self._recording_settings("Family car")
        item = {
            "filename": "cam_same_slug.mp4",
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": 9,
        }
        first_payload = b"vehicle-a"
        second_payload = b"vehicle-b"
        first_client = PayloadRecordingClient(item, first_payload)
        second_client = PayloadRecordingClient(item, second_payload)

        self.engine._collect_recordings(first_client, first_settings, RunTotals())
        second_settings = self.db.save_settings(
            {
                "vehicle": {
                    "name": "Family car",
                    "device_id": "other-stable-device",
                    "device_token": "other-stable-device-12345678",
                }
            }
        )
        self.engine._collect_recordings(second_client, second_settings, RunTotals())

        archived = self.db.list_items(category="recordings")
        self.assertEqual(first_client.downloads, 1)
        self.assertEqual(second_client.downloads, 1)
        self.assertEqual(len(archived), 2)
        self.assertEqual(len({item["relative_path"] for item in archived}), 2)
        self.assertEqual(
            {
                (self.engine.archive_root / item["relative_path"]).read_bytes()
                for item in archived
            },
            {first_payload, second_payload},
        )

    def test_sync_lazily_separates_a_legacy_shared_inventory_path(self) -> None:
        settings = self._recording_settings()
        identity = self.engine._vehicle_identity(settings)
        filename = "cam_legacy_shared.mp4"
        source_key = f"{identity}:recording:{filename}:{RECORDING_TIMESTAMP}"
        alias_key = (
            f"vehicle-legacy-alias:recording:{filename}:{RECORDING_TIMESTAMP}"
        )
        legacy_relative = (
            Path(settings["destination"]["subdirectory"])
            / self.engine._vehicle_slug(settings)
            / "recordings"
            / "drive"
            / filename
        )
        legacy_path = self.engine.archive_root / legacy_relative
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_payload = b"shared-old"
        legacy_path.write_bytes(legacy_payload)
        for key in (source_key, alias_key):
            self.assertTrue(
                self.db.add_item(
                    source_key=key,
                    category="recordings",
                    subtype="drive",
                    vehicle=self.engine._vehicle_slug(settings),
                    filename=filename,
                    relative_path=str(legacy_relative),
                    media_type="video/mp4",
                    size_bytes=len(legacy_payload),
                    sha256=hashlib.sha256(legacy_payload).hexdigest(),
                    source_timestamp=RECORDING_TIMESTAMP,
                    metadata={},
                )
            )
        current_payload = b"current-new-payload"
        item = {
            "filename": filename,
            "type": "normal",
            "timestamp": RECORDING_TIMESTAMP,
            "size": len(current_payload),
        }
        client = PayloadRecordingClient(item, current_payload)

        self.engine._collect_recordings(client, settings, RunTotals())

        current = self.db.get_item_by_source_key(source_key)
        alias = self.db.get_item_by_source_key(alias_key)
        self.assertEqual(client.downloads, 1)
        self.assertIsNotNone(current)
        self.assertIsNotNone(alias)
        self.assertNotEqual(current["relative_path"], alias["relative_path"])
        self.assertEqual(legacy_path.read_bytes(), legacy_payload)
        self.assertEqual(
            (self.engine.archive_root / current["relative_path"]).read_bytes(),
            current_payload,
        )

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

    def test_uncertain_saved_identity_uses_and_then_caches_a_status_probe(
        self,
    ) -> None:
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
        observed_settings = {
            **settings,
            "vehicle": {
                **settings["vehicle"],
                "device_id": "status-stable-device",
            },
        }
        observed_identity = self.engine._vehicle_identity(observed_settings)
        self.assertTrue(
            self.engine.can_start_recording_restore(observed_identity),
            "an access-code configuration must be allowed to probe /status",
        )

        class StatusRecordingClient(FakeRecordingClient):
            def status(self):
                return {
                    "deviceId": "status-stable-device",
                    "network": {"type": "wifi"},
                }

        with patch.object(
            self.engine, "_client", return_value=StatusRecordingClient()
        ):
            self.engine.run_once("manual")

        self.assertTrue(self.engine.can_start_recording_restore(observed_identity))
        self.assertFalse(
            self.engine.can_start_recording_restore("vehicle-not-observed")
        )
        self.assertEqual(self.db.get_settings()["vehicle"]["device_id"], "")

    def test_restore_probe_stops_after_status_when_vehicle_does_not_match(
        self,
    ) -> None:
        self._recording_settings("Car A")
        self.db.save_settings(
            {
                "vehicle": {
                    "device_id": "",
                    "device_token": "12345678",
                    "auto_detect_profile": False,
                }
            }
        )
        source_key = (
            f"vehicle-other:recording:cam_other.mp4:{RECORDING_TIMESTAMP}"
        )
        self.assertTrue(
            self.db.add_item(
                source_key=source_key,
                category="recordings",
                subtype="drive",
                vehicle="other-car",
                filename="cam_other.mp4",
                relative_path="vehicles/other-car/cam_other.mp4",
                media_type="video/mp4",
                size_bytes=10,
                sha256="a" * 64,
                source_timestamp=RECORDING_TIMESTAMP,
                metadata={},
            )
        )
        item = self.db.get_item_by_source_key(source_key)
        self.assertTrue(self.db.delete_archive_item(int(item["id"])))
        self.assertEqual(self.db.request_recording_restore(source_key), "vehicle-other")

        class ProbeOnlyClient:
            @staticmethod
            def status():
                return {
                    "deviceId": "current-status-device",
                    "network": {"type": "wifi"},
                }

            def __getattr__(self, name):
                raise AssertionError(f"restore probe called unexpected method {name}")

        with patch.object(self.engine, "_client", return_value=ProbeOnlyClient()):
            result = self.engine.run_once("restore")

        self.assertEqual(result["status"], "skipped")
        self.assertIn("another vehicle", result["message"])
        self.assertTrue(self.db.recording_restore_requested(source_key))

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
