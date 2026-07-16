from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .config import (
    CATEGORIES,
    discovered_vehicle_changes,
    next_run_at,
    slugify,
    wifi_policy,
)
from .db import Database
from .overdrive import OverdriveClient, OverdriveError


log = logging.getLogger("overdrive_archive.sync")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_SAFE_SOURCE_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
_CONFIG_CONTAINER_KEYS = {
    "appearance",
    "camera",
    "charginganalytics",
    "config",
    "display",
    "features",
    "oemdashcam",
    "proximityguard",
    "recording",
    "roadsense",
    "streaming",
    "surveillance",
    "telemetryoverlay",
    "triggers",
    "units",
    "vehicle",
}
_CONFIG_SCALAR_KEYS = {
    "audioenabled",
    "bitrate",
    "bitratebudget",
    "codec",
    "color",
    "cooldownseconds",
    "dark",
    "disablenativedvr",
    "distanceunit",
    "driveside",
    "enabled",
    "fontscale",
    "fps",
    "language",
    "lastmodified",
    "locale",
    "manualoverride",
    "modelid",
    "modelname",
    "oemdashcamenabled",
    "panoenabled",
    "postrecordseconds",
    "prerecordseconds",
    "quality",
    "recordingmode",
    "recordingquality",
    "resolution",
    "success",
    "surveillancemode",
    "surveillancequality",
    "targetfps",
    "telemetryoverlayenabled",
    "theme",
    "triggerlevel",
    "version",
}
_POLICY_RETRY_SECONDS = 5 * 60


class PolicyPause(OverdriveError):
    """Raised when a configurable network policy asks the run to stop."""


@dataclass
class RunTotals:
    items_added: int = 0
    items_skipped: int = 0
    error_count: int = 0
    bytes_added: int = 0


def _filename_subtype(filename: str) -> str:
    lower_name = filename.lower()
    if lower_name.startswith("replay_"):
        return "replay"
    if lower_name.startswith("dvr_"):
        return "oem_dashcam"
    if lower_name.startswith("event_"):
        return "surveillance"
    if lower_name.startswith("proximity_"):
        return "proximity"
    if lower_name.startswith("cam"):
        return "drive"
    return "unknown"


def _unknown_type_slug(value: str) -> str:
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    snake = re.sub(r"[^A-Za-z0-9_-]+", "_", snake).strip("_-").lower()
    return snake[:40] or "unknown"


def recording_subtype(item: dict[str, Any], filename: str) -> str:
    """Prefer Overdrive's type and retain filename compatibility with older builds."""
    source_type = str(item.get("type") or "").strip()
    known = {
        "replay": "replay",
        "sentry": "surveillance",
        "proximity": "proximity",
        "oemDashcam": "oem_dashcam",
        "oem_dashcam": "oem_dashcam",
    }
    if source_type in known:
        return known[source_type]
    if source_type == "normal":
        legacy = _filename_subtype(filename)
        return legacy if legacy in {"replay", "oem_dashcam"} else "drive"
    if _SAFE_SOURCE_TYPE.fullmatch(source_type):
        return _unknown_type_slug(source_type)
    return _filename_subtype(filename)


def recording_selection_key(subtype: str) -> str | None:
    return {
        "drive": "normal",
        "replay": "replay",
        "surveillance": "sentry",
        "proximity": "proximity",
        "oem_dashcam": "oemDashcam",
    }.get(subtype)


def _camera_layout_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = [payload]
    for key in ("event", "metadata", "recording"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for key in (
            "archiveCameraLayout",
            "cameraLayout",
            "recordingLayout",
            "layout",
        ):
            layout = str(candidate.get(key) or "").strip().lower()
            if layout in {"standard", "dashcam", "single"}:
                return layout
    return ""


def recording_camera_layout(
    item: dict[str, Any],
    subtype: str,
    settings: dict[str, Any],
    event_payload: dict[str, Any] | None = None,
) -> str:
    """Resolve how a composed recording should be cropped during playback."""
    if subtype == "oem_dashcam":
        return "single"
    detected = _camera_layout_from_payload(event_payload) or _camera_layout_from_payload(
        item
    )
    if detected:
        return detected
    vehicle = settings.get("vehicle")
    if isinstance(vehicle, dict):
        key = (
            "surveillance_layout"
            if subtype in {"surveillance", "proximity"}
            else "recording_layout"
        )
        configured = str(vehicle.get(key) or "").strip().lower()
        if configured in {"standard", "dashcam"}:
            return configured
    if subtype in {"drive", "replay", "surveillance", "proximity"}:
        return "standard"
    return "single"


class SyncEngine:
    def __init__(self, db: Database, archive_root: Path):
        self.db = db
        self.archive_root = archive_root
        self.archive_root.mkdir(parents=True, exist_ok=True)
        self.max_recording_bytes = int(
            float(os.environ.get("ARCHIVE_MAX_RECORDING_GB", "20"))
            * 1024
            * 1024
            * 1024
        )
        self._state_lock = threading.Lock()
        self._active = False
        self._current: dict[str, Any] = {}
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None

    def start_scheduler(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="archive-scheduler",
            daemon=True,
        )
        self._scheduler_thread.start()

    def stop(self) -> None:
        self._scheduler_stop.set()

    def trigger(self, reason: str = "manual") -> bool:
        with self._state_lock:
            if self._active:
                return False
            self._active = True
            self._current = {
                "active": True,
                "reason": reason,
                "stage": "queued",
                "current": "",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        thread = threading.Thread(
            target=self._thread_run,
            args=(reason,),
            name=f"archive-sync-{reason}",
            daemon=True,
        )
        thread.start()
        return True

    def state(self) -> dict[str, Any]:
        settings = self.db.get_settings()
        due = self._next_run_at(settings)
        with self._state_lock:
            current = dict(self._current)
            current["active"] = self._active
        current["next_run_at"] = (
            due.isoformat(timespec="seconds") if due is not None else None
        )
        return current

    def _set_state(self, **changes: Any) -> None:
        with self._state_lock:
            self._current.update(changes)

    def _thread_run(self, reason: str) -> None:
        try:
            self.run_once(reason)
        except Exception:
            log.exception("Unexpected sync failure")
        finally:
            with self._state_lock:
                self._active = False
                self._current["active"] = False
                self._current["stage"] = "idle"
                self._current["current"] = ""

    def _scheduler_loop(self) -> None:
        while not self._scheduler_stop.wait(15):
            try:
                settings = self.db.get_settings()
                due = self._next_run_at(settings)
                if due is not None and due <= datetime.now(timezone.utc):
                    self.trigger("schedule")
            except Exception:
                log.exception("Scheduler check failed")

    def _next_run_at(
        self,
        settings: dict[str, Any],
        now: datetime | None = None,
    ) -> datetime | None:
        schedule = settings["schedule"]
        if not schedule["enabled"] or schedule["mode"] == "manual":
            return None
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        latest = self.db.last_scheduled_run()
        last_started: datetime | None = None
        if latest is not None:
            try:
                last_started = datetime.fromisoformat(str(latest["started_at"]))
            except (TypeError, ValueError):
                last_started = None
            if last_started is not None and last_started.tzinfo is None:
                last_started = last_started.replace(tzinfo=timezone.utc)
            message = str(latest.get("message") or "").casefold()
            policy_paused = latest.get("status") == "skipped" or (
                latest.get("status") == "partial"
                and (
                    "waiting for wi-fi" in message
                    or "allowed ssid" in message
                )
            )
            if policy_paused and last_started is not None:
                return last_started + timedelta(seconds=_POLICY_RETRY_SECONDS)

        due = next_run_at(settings, last_started, now)
        if schedule["mode"] != "daily" or last_started is None:
            return due

        local_zone = ZoneInfo(schedule["timezone"])
        local_now = now.astimezone(local_zone)
        last_local = last_started.astimezone(local_zone)
        hour, minute = (
            int(part) for part in schedule["daily_time"].split(":", 1)
        )
        today_slot = local_now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if last_local.date() < local_now.date() and today_slot <= local_now:
            return now
        return due

    def _client(self, settings: dict[str, Any]) -> OverdriveClient:
        vehicle = settings["vehicle"]
        return OverdriveClient(
            base_url=vehicle["base_url"],
            device_token=vehicle["device_token"],
            verify_tls=vehicle["verify_tls"],
            timeout=vehicle["request_timeout_seconds"],
        )

    def run_once(self, reason: str = "manual") -> dict[str, Any]:
        run_id = self.db.start_run(reason)
        totals = RunTotals()
        errors: list[str] = []
        network_type = "unknown"
        settings = self.db.get_settings()
        client = self._client(settings)
        self._set_state(stage="connecting", current="Authenticating with Overdrive")

        try:
            status_payload = client.status()
            status_device_id = str(status_payload.get("deviceId") or "").strip()
            if status_device_id and status_device_id != "unknown":
                settings["vehicle"]["device_id"] = status_device_id
            if settings["vehicle"].get("auto_detect_profile"):
                profile = client.discover_vehicle_profile(status_payload)
                discovered = discovered_vehicle_changes(
                    settings["vehicle"],
                    profile,
                )
                if discovered.get("device_id") == "unknown":
                    discovered.pop("device_id")
                if discovered:
                    settings = self.db.save_settings({"vehicle": discovered})
            network = status_payload.get("network")
            if not isinstance(network, dict):
                network = {}
            network_type = str(network.get("type") or "unknown")
            allowed, policy_message = wifi_policy(settings, network)
            if not allowed:
                self.db.finish_run(
                    run_id,
                    status="skipped",
                    items_added=0,
                    items_skipped=0,
                    error_count=0,
                    bytes_added=0,
                    network_type=network_type,
                    message=policy_message,
                )
                self._set_state(stage="waiting", current=policy_message)
                return {"status": "skipped", "message": policy_message}

            selected = set(settings["content"]["categories"])
            trip_cache: dict[str, Any] | None = None
            for category in CATEGORIES:
                if category not in selected:
                    continue
                self._set_state(
                    stage="syncing",
                    current=category.replace("_", " ").title(),
                )
                try:
                    if category == "recordings":
                        self._collect_recordings(client, settings, totals)
                    elif category == "trips":
                        trip_cache = self._collect_trips(client, settings, totals)
                    elif category == "charging":
                        self._collect_charging(client, settings, totals)
                    elif category == "automations":
                        self._collect_simple(
                            client,
                            settings,
                            totals,
                            "automations",
                            "/api/automations/list",
                        )
                    elif category == "key_mappings":
                        self._collect_simple(
                            client,
                            settings,
                            totals,
                            "key_mappings",
                            "/api/keymap/config",
                        )
                    elif category == "telemetry":
                        trip_cache = self._collect_telemetry(
                            client, settings, totals, trip_cache
                        )
                    elif category == "roadsense":
                        self._collect_roadsense(client, settings, totals)
                    elif category == "configuration":
                        self._collect_configuration(client, settings, totals)
                except PolicyPause:
                    raise
                except OverdriveError as exc:
                    totals.error_count += 1
                    errors.append(f"{category}: {exc}")
                    log.warning("Collector %s failed: %s", category, exc)
                except Exception as exc:
                    totals.error_count += 1
                    errors.append(f"{category}: unexpected collector failure")
                    log.exception("Collector %s failed unexpectedly: %s", category, exc)

            final_status = "partial" if errors else "success"
            message = (
                "; ".join(errors[:5])
                if errors
                else f"Archived {totals.items_added} new item(s)."
            )
        except PolicyPause as exc:
            final_status = "partial" if totals.items_added else "skipped"
            message = str(exc)
        except OverdriveError as exc:
            totals.error_count += 1
            final_status = "failed"
            message = str(exc)
        except Exception:
            totals.error_count += 1
            final_status = "failed"
            message = "Unexpected synchronization failure. Check the container logs."
            log.exception("Sync run %s failed", run_id)

        self.db.finish_run(
            run_id,
            status=final_status,
            items_added=totals.items_added,
            items_skipped=totals.items_skipped,
            error_count=totals.error_count,
            bytes_added=totals.bytes_added,
            network_type=network_type,
            message=message,
        )
        self._set_state(stage="complete", current=message)
        return {
            "status": final_status,
            "message": message,
            "items_added": totals.items_added,
            "items_skipped": totals.items_skipped,
            "errors": totals.error_count,
            "bytes_added": totals.bytes_added,
        }

    def _destination_base(self, settings: dict[str, Any]) -> Path:
        relative = Path(settings["destination"]["subdirectory"])
        destination = (self.archive_root / relative).resolve()
        root = self.archive_root.resolve()
        destination.relative_to(root)
        destination.mkdir(parents=True, exist_ok=True)
        return destination

    def _vehicle_slug(self, settings: dict[str, Any]) -> str:
        return slugify(settings["vehicle"]["name"])

    def _vehicle_identity(self, settings: dict[str, Any]) -> str:
        vehicle = settings["vehicle"]
        device_id = str(vehicle.get("device_id") or "").strip()
        if device_id and device_id != "unknown":
            seed = f"device-id:{device_id.casefold()}"
        else:
            token = str(vehicle.get("device_token") or "").strip()
            token_prefix = token.rsplit("-", 1)[0].strip() if "-" in token else ""
            if token_prefix:
                seed = f"device-id:{token_prefix.casefold()}"
            else:
                seed = f"endpoint:{str(vehicle.get('base_url') or '').casefold()}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return f"vehicle-{digest[:24]}"

    def _temporary_path(self, destination: Path) -> Path:
        for _ in range(20):
            candidate = destination.with_name(
                f".{destination.name}.{secrets.token_hex(12)}.part"
            )
            if not candidate.exists():
                return candidate
        raise OverdriveError("Could not allocate a private temporary archive path.")

    def _safe_archive_path(self, relative: Path) -> Path:
        path = (self.archive_root / relative).resolve()
        path.relative_to(self.archive_root.resolve())
        return path

    def _safe_filename(self, value: Any) -> str:
        filename = str(value or "")
        if (
            not _SAFE_FILENAME.fullmatch(filename)
            or Path(filename).name != filename
            or not filename.lower().endswith(".mp4")
        ):
            raise OverdriveError("Vehicle returned an unsafe recording filename.")
        return filename

    def _recording_iter(
        self,
        client: OverdriveClient,
        types: list[str],
        severities: list[str],
        include_unknown: bool,
    ):
        selected = set(types)
        selected_severities = set(severities)
        if not selected and not include_unknown:
            return
        seen: set[str] = set()
        # Fetch the complete list and apply policy locally. This preserves new
        # Overdrive types that this release does not know about yet.
        for item in client.iter_recordings([], []):
            filename = str(item.get("filename") or "")
            subtype = recording_subtype(item, filename)
            selection_key = recording_selection_key(subtype)
            if selection_key is None:
                if not include_unknown:
                    continue
            elif selection_key not in selected:
                continue
            if subtype in {"surveillance", "proximity"} and selected_severities:
                severity = str(item.get("peakSeverity") or "").upper()
                if severity and severity not in selected_severities:
                    continue
            if filename and filename not in seen:
                seen.add(filename)
                yield item

    def _collect_recordings(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
    ) -> None:
        content = settings["content"]
        vehicle = self._vehicle_slug(settings)
        identity = self._vehicle_identity(settings)
        self._destination_base(settings)
        policy_check = self._download_policy_check(client, settings)

        for item in self._recording_iter(
            client,
            content["recording_types"],
            content["severities"],
            content["include_unknown_recording_types"],
        ):
            filename = self._safe_filename(item.get("filename"))
            subtype = recording_subtype(item, filename)
            timestamp_ms = int(item.get("timestamp") or 0)
            expected_size = max(0, int(item.get("size") or 0))
            source_key = f"{identity}:recording:{filename}:{timestamp_ms}"

            date = (
                datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)
                if timestamp_ms > 0
                else datetime.now(timezone.utc)
            )
            relative = (
                Path(settings["destination"]["subdirectory"])
                / vehicle
                / "recordings"
                / subtype
                / f"{date:%Y}"
                / f"{date:%m}"
                / f"{date:%d}"
                / filename
            )
            existing = self.db.get_item_by_source_key(source_key)
            if existing is not None:
                try:
                    existing_relative = Path(str(existing["relative_path"]))
                    final_path = self._safe_archive_path(existing_relative)
                    relative = existing_relative
                except (KeyError, OSError, TypeError, ValueError):
                    final_path = self._safe_archive_path(relative)
            else:
                final_path = self._safe_archive_path(relative)
            final_path.parent.mkdir(parents=True, exist_ok=True)

            if existing is not None and final_path.is_file():
                actual_size = final_path.stat().st_size
                required_size = expected_size or max(
                    0, int(existing.get("size_bytes") or 0)
                )
                if not required_size or actual_size == required_size:
                    if content["include_thumbnails"]:
                        self._ensure_recording_thumbnail(
                            client,
                            item,
                            final_path,
                        )
                    archive_metadata = self._prepare_recording_metadata(
                        client,
                        item,
                        subtype,
                        filename,
                        final_path,
                        settings,
                    )
                    digest = str(existing.get("sha256") or "")
                    if not digest:
                        _size, digest = self._hash_file(final_path)
                    updated = self.db.update_item(
                        source_key=source_key,
                        category="recordings",
                        subtype=subtype,
                        vehicle=vehicle,
                        filename=filename,
                        relative_path=str(relative),
                        media_type="video/mp4",
                        size_bytes=actual_size,
                        sha256=digest,
                        source_timestamp=timestamp_ms or None,
                        metadata=archive_metadata,
                    )
                    if not updated:
                        raise OverdriveError(
                            f"Could not refresh the inventory entry for {filename}."
                        )
                    totals.items_skipped += 1
                    continue

            needs_download = not final_path.is_file()
            if not needs_download:
                size, digest = self._hash_file(final_path)
                needs_download = bool(expected_size and size != expected_size)

            if needs_download:
                self._set_state(stage="downloading", current=filename)
                partial = self._temporary_path(final_path)
                try:
                    size, digest = client.download_to(
                        str(item.get("videoUrl") or f"/video/{client.encoded_filename(filename)}"),
                        partial,
                        max_bytes=self.max_recording_bytes,
                        policy_check=policy_check,
                    )
                    if expected_size and size != expected_size:
                        raise OverdriveError(
                            f"Recording size mismatch for {filename}: expected {expected_size}, received {size}."
                        )
                    os.replace(partial, final_path)
                    try:
                        os.chmod(final_path, 0o600)
                    except OSError:
                        pass
                    totals.bytes_added += size
                finally:
                    try:
                        partial.unlink(missing_ok=True)
                    except OSError:
                        pass

            if content["include_thumbnails"]:
                self._ensure_recording_thumbnail(
                    client,
                    item,
                    final_path,
                )
            archive_metadata = self._prepare_recording_metadata(
                client,
                item,
                subtype,
                filename,
                final_path,
                settings,
            )

            if existing is not None:
                updated = self.db.update_item(
                    source_key=source_key,
                    category="recordings",
                    subtype=subtype,
                    vehicle=vehicle,
                    filename=filename,
                    relative_path=str(relative),
                    media_type="video/mp4",
                    size_bytes=size,
                    sha256=digest,
                    source_timestamp=timestamp_ms or None,
                    metadata=archive_metadata,
                )
                if updated:
                    totals.items_skipped += 1
                else:
                    raise OverdriveError(
                        f"Could not update the repaired inventory entry for {filename}."
                    )
            else:
                added = self.db.add_item(
                    source_key=source_key,
                    category="recordings",
                    subtype=subtype,
                    vehicle=vehicle,
                    filename=filename,
                    relative_path=str(relative),
                    media_type="video/mp4",
                    size_bytes=size,
                    sha256=digest,
                    source_timestamp=timestamp_ms or None,
                    metadata=archive_metadata,
                )
                if added:
                    totals.items_added += 1
                else:
                    totals.items_skipped += 1

    def _prepare_recording_metadata(
        self,
        client: OverdriveClient,
        item: dict[str, Any],
        subtype: str,
        filename: str,
        final_path: Path,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        event_payload: dict[str, Any] | None = None
        content = settings["content"]
        if content["include_event_timeline"] and (
            item.get("peakSeverity")
            or str(item.get("type") or "") in {"sentry", "proximity"}
        ):
            event_payload = self._download_optional_json(
                client,
                f"/api/events/{client.encoded_filename(filename)}",
                final_path.with_suffix(".events.json"),
            )
        archive_metadata = dict(item)
        archive_metadata["archiveRecordingSubtype"] = subtype
        archive_metadata["archiveCameraLayout"] = recording_camera_layout(
            item,
            subtype,
            settings,
            event_payload,
        )
        self._write_json(
            final_path.with_suffix(".metadata.json"),
            archive_metadata,
        )
        return archive_metadata

    def _collect_trips(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
    ) -> dict[str, Any]:
        range_params = {"from": 1, "to": int(time.time() * 1000)}
        payload = client.fetch_paginated(
            "/api/trips",
            "trips",
            extra_params=range_params,
        )
        self._archive_snapshot(settings, totals, "trips", payload)
        return payload

    def _collect_charging(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
    ) -> None:
        payload = client.fetch_paginated(
            "/api/charging",
            "sessions",
            extra_params={"days": 0},
        )
        self._archive_snapshot(settings, totals, "charging", payload)

    def _collect_simple(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
        category: str,
        path: str,
    ) -> None:
        self._archive_snapshot(
            settings,
            totals,
            category,
            client.get_json(path),
        )

    def _collect_telemetry(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
        trip_cache: dict[str, Any] | None,
    ) -> dict[str, Any]:
        current = client.get_json("/api/mqtt/telemetry")
        self._archive_snapshot(settings, totals, "telemetry", current, "live")

        if trip_cache is None:
            range_params = {"from": 1, "to": int(time.time() * 1000)}
            trip_cache = client.fetch_paginated(
                "/api/trips",
                "trips",
                extra_params=range_params,
            )
        trips = trip_cache.get("trips")
        if not isinstance(trips, list):
            return trip_cache
        identity = self._vehicle_identity(settings)
        for trip in trips:
            if not isinstance(trip, dict):
                continue
            trip_id = trip.get("id")
            if not isinstance(trip_id, int) and not (
                isinstance(trip_id, str) and trip_id.isdigit()
            ):
                continue
            trip_id = int(trip_id)
            start_time = int(trip.get("startTime") or 0)
            source_key = f"{identity}:trip-telemetry:{trip_id}:{start_time}"
            if self.db.has_item(source_key):
                totals.items_skipped += 1
                continue
            telemetry = client.get_json(
                f"/api/trips/{trip_id}/telemetry",
                max_bytes=128 * 1024 * 1024,
            )
            try:
                gps = client.get_json(
                    f"/api/trips/{trip_id}/gps",
                    max_bytes=64 * 1024 * 1024,
                )
            except OverdriveError as exc:
                gps = {"unavailable": str(exc)}
            payload = {"trip_id": trip_id, "trip": trip, "telemetry": telemetry, "gps": gps}
            self._archive_snapshot(
                settings,
                totals,
                "telemetry",
                payload,
                f"trip-{trip_id}",
                source_key=source_key,
                source_timestamp=start_time or None,
            )
        return trip_cache

    def _collect_roadsense(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
    ) -> None:
        features: dict[str, dict[str, Any]] = {}
        lat_edges = (-85, -45, 0, 45, 85)
        lon_edges = (-180, -120, -60, 0, 60, 120, 180)
        for lat_index in range(len(lat_edges) - 1):
            for lon_index in range(len(lon_edges) - 1):
                bbox = (
                    lon_edges[lon_index],
                    lat_edges[lat_index],
                    lon_edges[lon_index + 1],
                    lat_edges[lat_index + 1],
                )
                path = "/api/roadsense/hazards?bbox=" + ",".join(
                    str(value) for value in bbox
                )
                payload = client.get_json(path)
                page_features = payload.get("features")
                if not isinstance(page_features, list):
                    continue
                for feature in page_features:
                    if not isinstance(feature, dict):
                        continue
                    key = hashlib.sha256(
                        json.dumps(
                            feature, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest()
                    features[key] = feature
        self._archive_snapshot(
            settings,
            totals,
            "roadsense",
            {
                "type": "FeatureCollection",
                "features": list(features.values()),
                "note": "Collected from the viewport API in geographic tiles.",
            },
        )

    def _collect_configuration(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
    ) -> None:
        payload = client.get_json("/api/settings/unified")
        redacted = self._redact_configuration(payload)
        self._archive_snapshot(settings, totals, "configuration", redacted)

    def _archive_snapshot(
        self,
        settings: dict[str, Any],
        totals: RunTotals,
        category: str,
        payload: dict[str, Any],
        label: str = "snapshot",
        *,
        source_key: str | None = None,
        source_timestamp: int | None = None,
    ) -> None:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        vehicle = self._vehicle_slug(settings)
        identity = self._vehicle_identity(settings)
        source_key = source_key or f"{identity}:{category}:{digest}"
        if self.db.has_item(source_key):
            totals.items_skipped += 1
            return
        now = datetime.now(timezone.utc)
        safe_label = re.sub(r"[^a-zA-Z0-9._-]+", "-", label).strip("-") or "snapshot"
        filename = f"{now:%Y%m%dT%H%M%SZ}-{safe_label}-{digest[:10]}.json"
        relative = (
            Path(settings["destination"]["subdirectory"])
            / vehicle
            / category
            / f"{now:%Y}"
            / f"{now:%m}"
            / filename
        )
        destination = (self.archive_root / relative).resolve()
        destination.relative_to(self.archive_root.resolve())
        self._write_bytes(destination, canonical + b"\n")
        added = self.db.add_item(
            source_key=source_key,
            category=category,
            subtype="",
            vehicle=vehicle,
            filename=filename,
            relative_path=str(relative),
            media_type="application/json",
            size_bytes=len(canonical) + 1,
            sha256=digest,
            source_timestamp=source_timestamp,
            metadata={"label": label, "category": category},
        )
        if added:
            totals.items_added += 1
            totals.bytes_added += len(canonical) + 1
        else:
            totals.items_skipped += 1

    def _download_policy_check(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
    ) -> Callable[[], None]:
        last_check = 0.0

        def check() -> None:
            nonlocal last_check
            now = time.monotonic()
            if now - last_check < 30:
                return
            last_check = now
            status = client.status()
            network = status.get("network")
            allowed, message = wifi_policy(
                settings, network if isinstance(network, dict) else {}
            )
            if not allowed:
                raise PolicyPause(message)

        return check

    def _download_optional(
        self,
        client: OverdriveClient,
        source_path: str,
        destination: Path,
        max_bytes: int,
    ) -> None:
        if not source_path or destination.exists():
            return
        partial = self._temporary_path(destination)
        try:
            client.download_to(source_path, partial, max_bytes=max_bytes)
            os.replace(partial, destination)
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
        except OverdriveError as exc:
            log.info("Optional artifact unavailable: %s", exc)
        finally:
            partial.unlink(missing_ok=True)

    def _ensure_recording_thumbnail(
        self,
        client: OverdriveClient,
        item: dict[str, Any],
        video_path: Path,
    ) -> None:
        destination = video_path.with_suffix(".jpg")
        if destination.is_file():
            return
        self._download_optional(
            client,
            str(
                item.get("heroThumbnailUrl")
                or item.get("thumbnailUrl")
                or ""
            ),
            destination,
            20 * 1024 * 1024,
        )
        if destination.is_file():
            return
        self._generate_recording_thumbnail(video_path, destination)

    def _generate_recording_thumbnail(
        self,
        video_path: Path,
        destination: Path,
    ) -> bool:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            log.info("No ffmpeg binary is available for local thumbnail generation.")
            return False
        partial = self._temporary_path(destination)
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    "1",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=640:-2:force_original_aspect_ratio=decrease",
                    "-q:v",
                    "3",
                    "-threads",
                    "1",
                    "-f",
                    "image2",
                    "-y",
                    str(partial),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=25,
            )
            if not partial.is_file() or partial.stat().st_size < 500:
                raise OSError("generated thumbnail is empty")
            with partial.open("rb") as handle:
                if handle.read(2) != b"\xff\xd8":
                    raise OSError("generated thumbnail is not JPEG")
            os.replace(partial, destination)
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            log.info(
                "Could not generate a thumbnail for %s: %s",
                video_path.name,
                exc,
            )
            return False
        finally:
            partial.unlink(missing_ok=True)

    def _download_optional_json(
        self,
        client: OverdriveClient,
        source_path: str,
        destination: Path,
    ) -> dict[str, Any] | None:
        if destination.exists():
            try:
                if destination.stat().st_size > 32 * 1024 * 1024:
                    return None
                payload = json.loads(destination.read_text(encoding="utf-8"))
                return payload if isinstance(payload, dict) else None
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return None
        try:
            payload = client.get_json(source_path, max_bytes=32 * 1024 * 1024)
            self._write_json(destination, payload)
            return payload
        except OverdriveError as exc:
            log.info("Optional JSON artifact unavailable: %s", exc)
            return None

    def _write_json(self, destination: Path, payload: Any) -> None:
        raw = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8") + b"\n"
        self._write_bytes(destination, raw)

    def _write_bytes(self, destination: Path, raw: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = self._temporary_path(destination)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(partial, flags, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(partial, destination)
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
        finally:
            partial.unlink(missing_ok=True)

    def _hash_file(self, path: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
        return size, digest.hexdigest()

    def _redact_configuration(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            normalized = re.sub(r"[^a-z0-9]", "", key_text.lower())
            if normalized in _CONFIG_CONTAINER_KEYS and isinstance(child, dict):
                nested = self._redact_configuration(child)
                if nested:
                    result[key_text] = nested
                continue
            if normalized not in _CONFIG_SCALAR_KEYS:
                continue
            if not isinstance(child, (bool, int, float, str)):
                continue
            if isinstance(child, str):
                if len(child) > 200:
                    continue
                parsed = urlsplit(child)
                if parsed.scheme or parsed.netloc:
                    continue
            result[key_text] = child
        return result
