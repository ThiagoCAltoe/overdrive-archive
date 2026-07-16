from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import stat
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
from .overdrive import OverdriveClient, OverdriveError, is_bearer_jwt


log = logging.getLogger("overdrive_archive.sync")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_SAFE_SOURCE_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
_RETENTION_STAGE = re.compile(
    r"^\.retention-(?P<item_id>[1-9][0-9]*)-(?P<nonce>[0-9a-f]{24})\.pending$"
)
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


class SyncCancelled(Exception):
    """Raised at a safe checkpoint after the operator requests Stop."""


@dataclass
class RunTotals:
    items_added: int = 0
    items_skipped: int = 0
    error_count: int = 0
    bytes_added: int = 0


@dataclass(frozen=True)
class RecordingQueueEntry:
    item: dict[str, Any]
    source_key: str
    filename: str
    subtype: str
    timestamp_ms: int
    expected_size: int
    relative: Path
    final_path: Path
    partial_path: Path
    existing: dict[str, Any] | None
    needs_download: bool
    partial_size: int
    known_before_run: bool


def recording_queue_priority(entry: RecordingQueueEntry) -> tuple[int, int, int, str]:
    """Match the dashboard queue: partials, prior backlog, then new items."""
    timestamp = entry.timestamp_ms if entry.timestamp_ms > 0 else 2**63 - 1
    if entry.partial_size > 0:
        remaining = (
            max(0, entry.expected_size - entry.partial_size)
            if entry.expected_size
            else 2**63 - 1
        )
        return (0, remaining, timestamp, entry.filename)
    return (
        1 if entry.known_before_run else 2,
        timestamp,
        0,
        entry.filename,
    )


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
        self._cancel_event: threading.Event | None = None
        self._sync_thread: threading.Thread | None = None
        self._retention_lock = threading.Lock()
        self._retention_active = False
        self._last_retention_check = 0.0
        self._observed_vehicle_connection = ""
        self._observed_vehicle_identity = ""
        self._recover_retention_deletions()

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
        self.request_stop()
        scheduler = self._scheduler_thread
        if scheduler is not None and scheduler is not threading.current_thread():
            scheduler.join()
        # Retention moves files and commits a durable journal. Let an active
        # operation reach a recoverable boundary before the process exits.
        self._retention_lock.acquire()
        self._retention_lock.release()

    def request_stop(self) -> bool:
        """Request cooperative cancellation without freeing the active slot."""
        with self._state_lock:
            if not self._active or self._cancel_event is None:
                return False
            self._cancel_event.set()
            self._current.update(
                {
                    "stop_requested": True,
                    "stage": "stopping",
                    "current": "Stopping synchronization…",
                }
            )
            return True

    def _check_cancelled(self) -> None:
        with self._state_lock:
            event = self._cancel_event
        if event is not None and event.is_set():
            raise SyncCancelled("Synchronization stopped by user.")

    def trigger(self, reason: str = "manual") -> bool:
        cancel_event = threading.Event()
        with self._state_lock:
            if self._active or self._retention_active:
                return False
            self._active = True
            self._cancel_event = cancel_event
            self._current = {
                "active": True,
                "reason": reason,
                "stage": "queued",
                "current": "",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "stop_requested": False,
                "run_id": None,
                "queue_bytes_done": 0,
                "queue_bytes_total": 0,
                "queue_items_done": 0,
                "queue_items_total": 0,
                "queue_unknown_sizes": 0,
                "queue_bytes_indeterminate": False,
            }
        thread = threading.Thread(
            target=self._thread_run,
            args=(reason, cancel_event),
            name=f"archive-sync-{reason}",
            daemon=True,
        )
        with self._state_lock:
            self._sync_thread = thread
        try:
            thread.start()
        except Exception:
            with self._state_lock:
                if self._cancel_event is cancel_event:
                    self._active = False
                    self._cancel_event = None
                    self._sync_thread = None
                    self._current.update(
                        {"active": False, "stage": "idle", "current": ""}
                    )
            raise
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

    def _thread_run(self, reason: str, cancel_event: threading.Event) -> None:
        try:
            self.run_once(reason)
        except Exception:
            log.exception("Unexpected sync failure")
        finally:
            with self._state_lock:
                if self._cancel_event is cancel_event:
                    self._active = False
                    self._cancel_event = None
                    self._sync_thread = None
                    self._current["active"] = False
                    self._current["stop_requested"] = False
                    self._current["stage"] = "idle"
                    self._current["current"] = ""

    def _scheduler_loop(self) -> None:
        while not self._scheduler_stop.wait(15):
            try:
                settings = self.db.get_settings()
                due = self._next_run_at(settings)
                if due is not None and due <= datetime.now(timezone.utc):
                    self.trigger("schedule")
                now = time.monotonic()
                if now - self._last_retention_check >= 60:
                    result = self.apply_retention(settings)
                    if result.get("status") != "deferred":
                        self._last_retention_check = now
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
        recovery_errors = self._recover_retention_deletions()
        if recovery_errors:
            log.warning(
                "Synchronization started with %s pending retention cleanup error(s)",
                recovery_errors,
            )
        run_id = self.db.start_run(reason)
        self._set_state(run_id=run_id)
        totals = RunTotals()
        errors: list[str] = []
        network_type = "unknown"
        settings = self.db.get_settings()
        connection_fingerprint = self._vehicle_connection_fingerprint(settings)
        client = self._client(settings)
        self._set_state(stage="connecting", current="Authenticating with Overdrive")

        try:
            self._check_cancelled()
            status_payload = client.status()
            self._check_cancelled()
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
                self._check_cancelled()
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
            current_identity = self._vehicle_identity(settings)
            with self._state_lock:
                self._observed_vehicle_connection = connection_fingerprint
                self._observed_vehicle_identity = current_identity
            pending_restore = self.db.has_pending_recording_restores(current_identity)
            if reason == "restore" and not pending_restore:
                message = "Requested recording belongs to another vehicle."
                self.db.finish_run(
                    run_id,
                    status="skipped",
                    items_added=0,
                    items_skipped=0,
                    error_count=0,
                    bytes_added=0,
                    network_type=network_type,
                    message=message,
                )
                self._set_state(stage="waiting", current=message)
                return {"status": "skipped", "message": message}
            if pending_restore:
                selected.add("recordings")
            trip_cache: dict[str, Any] | None = None
            for category in CATEGORIES:
                if category not in selected:
                    continue
                self._check_cancelled()
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
                except (PolicyPause, SyncCancelled):
                    raise
                except OverdriveError as exc:
                    totals.error_count += 1
                    errors.append(f"{category}: {exc}")
                    log.warning("Collector %s failed: %s", category, exc)
                except Exception as exc:
                    totals.error_count += 1
                    errors.append(f"{category}: unexpected collector failure")
                    log.exception("Collector %s failed unexpectedly: %s", category, exc)

            self._check_cancelled()
            final_status = "partial" if errors else "success"
            message = (
                "; ".join(errors[:5])
                if errors
                else f"Archived {totals.items_added} new item(s)."
            )
        except SyncCancelled as exc:
            final_status = "cancelled"
            message = str(exc)
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

        if final_status != "cancelled":
            try:
                self._check_cancelled()
                retention_result = self.apply_retention(self.db.get_settings())
                removed = int(retention_result.get("deleted_items") or 0)
                if removed:
                    message = f"{message} Retention removed {removed} local item(s)."
                if retention_result.get("limit_satisfied") is False:
                    message = (
                        f"{message} Storage limit could not be reached because "
                        "the remaining items are protected or unmanaged."
                    )
                retention_errors = int(retention_result.get("error_count") or 0)
                if retention_errors:
                    totals.error_count += retention_errors
                    if final_status == "success":
                        final_status = "partial"
                    message = f"{message} Retention could not remove some local items."
            except SyncCancelled as exc:
                final_status = "cancelled"
                message = str(exc)
            except Exception:
                totals.error_count += 1
                if final_status == "success":
                    final_status = "partial"
                message = f"{message} Local retention failed; check the container logs."
                log.exception("Retention failed after sync run %s", run_id)

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

    def apply_retention(
        self,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply local-only age and storage policies without touching the vehicle."""
        with self._state_lock:
            active_elsewhere = (
                self._active and threading.current_thread() is not self._sync_thread
            )
            shutting_down = self._scheduler_stop.is_set()
        if (
            shutting_down
            or active_elsewhere
            or not self._retention_lock.acquire(blocking=False)
        ):
            return {"status": "deferred", "deleted_items": 0, "deleted_bytes": 0}
        with self._state_lock:
            active_elsewhere = (
                self._active and threading.current_thread() is not self._sync_thread
            )
            if self._scheduler_stop.is_set() or active_elsewhere:
                self._retention_lock.release()
                return {"status": "deferred", "deleted_items": 0, "deleted_bytes": 0}
            self._retention_active = True
        try:
            recovery_errors = self._recover_retention_deletions()
            settings = settings or self.db.get_settings()
            retention = settings["retention"]
            category_rules = retention["categories"]
            storage_rule = retention["storage_limit"]
            if not storage_rule["enabled"] and not any(
                rule["enabled"] for rule in category_rules.values()
            ):
                return {
                    "status": "partial" if recovery_errors else "disabled",
                    "deleted_items": 0,
                    "deleted_bytes": 0,
                    "error_count": recovery_errors,
                }

            # Keep-latest is a rank across the complete local category. A
            # manually pinned item can occupy one of those newest slots while
            # remaining independently protected from every deletion policy.
            candidates = self.db.list_retention_candidates(include_protected=True)
            manually_protected = self.db.list_retention_protected_source_keys()
            protected_ids: set[int] = {
                int(item["id"])
                for item in candidates
                if str(item["source_key"]) in manually_protected
            }
            for category, rule in category_rules.items():
                if not rule["keep_latest_enabled"]:
                    continue
                category_items = [
                    item for item in candidates if item["category"] == category
                ]
                category_items.sort(
                    key=self._retention_item_sort_key,
                    reverse=True,
                )
                protected_ids.update(
                    int(item["id"])
                    for item in category_items[: int(rule["keep_latest_count"])]
                )

            now = datetime.now(timezone.utc)
            deleted_ids: set[int] = set()
            deleted_items = 0
            deleted_bytes = 0
            error_count = recovery_errors

            for item in candidates:
                self._check_cancelled()
                item_id = int(item["id"])
                rule = category_rules.get(str(item["category"]))
                if not rule or not rule["enabled"] or item_id in protected_ids:
                    continue
                seconds = int(rule["value"]) * {
                    "minutes": 60,
                    "hours": 3600,
                    "days": 86400,
                }[rule["unit"]]
                try:
                    cutoff = now - timedelta(seconds=seconds)
                except OverflowError:
                    # A valid, very large policy can reach farther back than
                    # datetime.min. Saturating means every representable item
                    # is correctly considered inside the retention window.
                    cutoff = datetime.min.replace(tzinfo=timezone.utc)
                if self._retention_item_datetime(item) >= cutoff:
                    continue
                deleted, freed, cleanup_error = self._delete_local_archive_item(item)
                if deleted:
                    deleted_ids.add(item_id)
                    deleted_items += 1
                    deleted_bytes += freed
                if cleanup_error:
                    error_count += 1

            usage = self._archive_usage_bytes()
            limit = int(storage_rule["max_bytes"]) if storage_rule["enabled"] else 0
            if limit and usage > limit:
                quota_candidates = [
                    item
                    for item in candidates
                    if int(item["id"]) not in deleted_ids
                    and int(item["id"]) not in protected_ids
                ]
                quota_candidates.sort(key=self._retention_item_sort_key)
                for item in quota_candidates:
                    self._check_cancelled()
                    if usage <= limit:
                        break
                    deleted, freed, cleanup_error = self._delete_local_archive_item(item)
                    if deleted:
                        deleted_ids.add(int(item["id"]))
                        deleted_items += 1
                        deleted_bytes += freed
                        usage = max(0, usage - freed)
                    if cleanup_error:
                        error_count += 1

            final_usage = self._archive_usage_bytes()
            satisfied = not limit or final_usage <= limit
            return {
                "status": "complete" if error_count == 0 else "partial",
                "deleted_items": deleted_items,
                "deleted_bytes": deleted_bytes,
                "error_count": error_count,
                "usage_bytes": final_usage,
                "limit_bytes": limit,
                "limit_satisfied": satisfied,
                "protected_items": len(protected_ids),
            }
        finally:
            with self._state_lock:
                self._retention_active = False
            self._retention_lock.release()

    @staticmethod
    def _retention_item_datetime(item: dict[str, Any]) -> datetime:
        try:
            timestamp = int(item.get("source_timestamp") or 0)
            if timestamp > 0:
                seconds = timestamp / 1000 if timestamp >= 10_000_000_000 else timestamp
                return datetime.fromtimestamp(seconds, timezone.utc)
        except (OSError, OverflowError, TypeError, ValueError):
            pass
        try:
            created = datetime.fromisoformat(str(item.get("created_at") or ""))
            return created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    @classmethod
    def _retention_item_sort_key(cls, item: dict[str, Any]) -> tuple[datetime, int]:
        return cls._retention_item_datetime(item), int(item["id"])

    def _retention_safe_path(self, relative_value: Any) -> Path:
        relative = Path(str(relative_value or ""))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError("Unsafe archived path.")
        root = self.archive_root.resolve()
        current = root
        for part in relative.parts[:-1]:
            current /= part
            if current.is_symlink():
                raise ValueError("Archived path traverses a symbolic link.")
        return root.joinpath(relative)

    @staticmethod
    def _retention_sidecar_paths(primary: Path, category: str) -> list[Path]:
        if category != "recordings":
            return []
        partial = primary.with_suffix(primary.suffix + ".part")
        return [
            primary.with_suffix(".jpg"),
            primary.with_suffix(".metadata.json"),
            primary.with_suffix(".events.json"),
            partial,
            partial.with_name(partial.name + ".meta"),
            partial.with_name(partial.name + ".complete.json"),
            partial.with_name(partial.name + ".ownership-conflict.json"),
        ]

    def _retention_recording_artifacts_in_use(
        self, primary: Path, category: str
    ) -> bool:
        """Protect recording bytes referenced by any vehicle or conflict marker."""
        if category != "recordings":
            return False
        partial = primary.with_suffix(primary.suffix + ".part")
        partial_relative = str(
            partial.relative_to(self.archive_root.resolve())
        )
        if self.db.recording_download_job_sources_for_partial(partial_relative):
            return True
        conflict = partial.with_name(
            partial.name + ".ownership-conflict.json"
        )
        return self._path_lstat(conflict) is not None

    @staticmethod
    def _path_lstat(path: Path) -> os.stat_result | None:
        try:
            return path.lstat()
        except FileNotFoundError:
            return None

    def _retention_job_paths(
        self, job: dict[str, Any]
    ) -> tuple[int, Path, Path]:
        item_id = int(job["item_id"])
        if item_id <= 0:
            raise ValueError("Invalid retention journal item id.")
        original = self._retention_safe_path(job.get("original_relative_path"))
        staged = self._retention_safe_path(job.get("staged_relative_path"))
        match = _RETENTION_STAGE.fullmatch(staged.name)
        if (
            staged.parent != original.parent
            or match is None
            or int(match.group("item_id")) != item_id
        ):
            raise ValueError("Invalid retention staging path.")
        return item_id, original, staged

    @staticmethod
    def _unlink_retention_paths(paths: list[Path]) -> tuple[int, bool]:
        freed = 0
        cleanup_ok = True
        for path in paths:
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                cleanup_ok = False
                continue
            if stat.S_ISDIR(info.st_mode):
                cleanup_ok = False
                continue
            try:
                path.unlink()
                if stat.S_ISREG(info.st_mode):
                    freed += max(0, int(info.st_size))
            except OSError:
                cleanup_ok = False
        return freed, cleanup_ok

    def _recover_retention_deletions(self) -> int:
        """Resolve durable staging jobs left at any prior crash boundary."""
        try:
            jobs = self.db.list_retention_deletion_jobs()
        except Exception:
            log.exception("Could not read the retention deletion journal")
            return 1
        errors = 0
        for job in jobs:
            try:
                item_id, original, staged = self._retention_job_paths(job)
            except (KeyError, OSError, TypeError, ValueError):
                log.error(
                    "Retention refused an invalid deletion journal row for item %s",
                    job.get("item_id"),
                )
                errors += 1
                continue

            if bool(job.get("inventory_present")):
                try:
                    original_info = self._path_lstat(original)
                    staged_info = self._path_lstat(staged)
                except OSError:
                    log.exception(
                        "Retention could not inspect staged item %s", item_id
                    )
                    errors += 1
                    continue
                if staged_info is not None:
                    if stat.S_ISDIR(staged_info.st_mode) or original_info is not None:
                        log.error(
                            "Retention preserved conflicting staged files for item %s",
                            item_id,
                        )
                        errors += 1
                        continue
                    try:
                        staged.replace(original)
                    except OSError:
                        log.exception(
                            "Retention could not restore staged item %s", item_id
                        )
                        errors += 1
                        continue
                try:
                    finished = self.db.finish_retention_deletion(item_id)
                except Exception:
                    log.exception(
                        "Retention could not finish rollback journal for item %s",
                        item_id,
                    )
                    errors += 1
                    continue
                if not finished:
                    errors += 1
                continue

            if not bool(job.get("tombstone_present")):
                log.error(
                    "Retention preserved an ambiguous deletion journal for item %s",
                    item_id,
                )
                errors += 1
                continue

            try:
                artifacts_in_use = self._retention_recording_artifacts_in_use(
                    original, str(job.get("category") or "")
                )
            except (OSError, TypeError, ValueError):
                log.exception(
                    "Retention could not verify recording jobs for item %s",
                    item_id,
                )
                errors += 1
                continue
            if artifacts_in_use:
                try:
                    original_info = self._path_lstat(original)
                    staged_info = self._path_lstat(staged)
                    if staged_info is not None:
                        if (
                            stat.S_ISDIR(staged_info.st_mode)
                            or original_info is not None
                        ):
                            raise OSError(
                                "conflicting primary paths block retention rollback"
                            )
                        staged.replace(original)
                except OSError:
                    log.exception(
                        "Retention could not preserve referenced item %s", item_id
                    )
                else:
                    log.warning(
                        "Retention deferred referenced recording item %s", item_id
                    )
                errors += 1
                continue

            try:
                shared_path = (
                    self.db.count_archive_path_references(
                        str(job.get("original_relative_path") or "")
                    )
                    > 0
                )
            except Exception:
                log.exception(
                    "Retention could not verify path ownership for item %s",
                    item_id,
                )
                errors += 1
                continue
            if shared_path:
                try:
                    original_info = self._path_lstat(original)
                    staged_info = self._path_lstat(staged)
                except OSError:
                    log.exception(
                        "Retention could not inspect shared staged item %s",
                        item_id,
                    )
                    errors += 1
                    continue
                if staged_info is not None:
                    if stat.S_ISDIR(staged_info.st_mode) or original_info is not None:
                        log.error(
                            "Retention preserved conflicting shared files for item %s",
                            item_id,
                        )
                        errors += 1
                        continue
                    try:
                        staged.replace(original)
                    except OSError:
                        log.exception(
                            "Retention could not restore shared item %s", item_id
                        )
                        errors += 1
                        continue
                try:
                    finished = self.db.finish_retention_deletion(item_id)
                except Exception:
                    log.exception(
                        "Retention could not finish shared cleanup journal for item %s",
                        item_id,
                    )
                    errors += 1
                    continue
                if not finished:
                    errors += 1
                continue

            cleanup_paths = [staged, original]
            cleanup_paths.extend(
                self._retention_sidecar_paths(
                    original, str(job.get("category") or "")
                )
            )
            _freed, cleanup_ok = self._unlink_retention_paths(cleanup_paths)
            if not cleanup_ok:
                log.warning(
                    "Retention will retry staged cleanup for item %s", item_id
                )
                errors += 1
                continue
            try:
                finished = self.db.finish_retention_deletion(item_id)
            except Exception:
                log.exception(
                    "Retention could not finish cleanup journal for item %s",
                    item_id,
                )
                errors += 1
                continue
            if not finished:
                errors += 1
        return errors

    def _delete_local_archive_item(
        self, item: dict[str, Any]
    ) -> tuple[bool, int, bool]:
        try:
            primary = self._retention_safe_path(item.get("relative_path"))
        except (OSError, TypeError, ValueError):
            log.error("Retention refused an unsafe archive item path for item %s", item.get("id"))
            return False, 0, True
        item_id = int(item["id"])
        category = str(item.get("category") or "")
        try:
            if self._retention_recording_artifacts_in_use(primary, category):
                log.warning(
                    "Retention deferred recording item %s because its artifacts "
                    "are still referenced",
                    item_id,
                )
                return False, 0, False
        except (OSError, TypeError, ValueError):
            log.exception(
                "Retention could not verify recording jobs for item %s", item_id
            )
            return False, 0, True
        try:
            shared_path = (
                self.db.count_archive_path_references(
                    str(item.get("relative_path") or "")
                )
                > 1
            )
        except Exception:
            log.exception(
                "Retention could not verify path ownership for item %s", item_id
            )
            return False, 0, True
        if shared_path:
            try:
                transitioned = self.db.delete_archive_item(item_id)
            except Exception:
                log.exception(
                    "Retention database transition failed for shared item %s",
                    item_id,
                )
                return False, 0, True
            return transitioned, 0, not transitioned

        staged_primary: Path | None = None
        for _ in range(20):
            candidate = primary.with_name(
                f".retention-{item_id}-{secrets.token_hex(12)}.pending"
            )
            try:
                if self._path_lstat(candidate) is None:
                    staged_primary = candidate
                    break
            except OSError:
                return False, 0, True
        if staged_primary is None:
            return False, 0, True
        try:
            staged_relative = staged_primary.relative_to(
                self.archive_root.resolve()
            )
            journal = self.db.prepare_retention_deletion(
                item_id, str(staged_relative)
            )
        except Exception:
            log.exception(
                "Retention could not prepare deletion journal for item %s", item_id
            )
            return False, 0, True
        if journal is None:
            return False, 0, True
        try:
            primary_info = self._path_lstat(primary)
            if primary_info is not None:
                if stat.S_ISDIR(primary_info.st_mode):
                    self._recover_retention_deletions()
                    return False, 0, True
                primary.replace(staged_primary)
        except OSError:
            self._recover_retention_deletions()
            return False, 0, True
        try:
            transitioned = self.db.delete_archive_item(item_id)
        except Exception:
            log.exception(
                "Retention database transition failed for item %s",
                item_id,
            )
            transitioned = False
        if not transitioned:
            self._recover_retention_deletions()
            return False, 0, True
        try:
            artifacts_in_use = self._retention_recording_artifacts_in_use(
                primary, category
            )
        except (OSError, TypeError, ValueError):
            log.exception(
                "Retention could not recheck recording jobs for item %s", item_id
            )
            artifacts_in_use = True
        if artifacts_in_use:
            try:
                if self._path_lstat(primary) is not None:
                    raise OSError(
                        "original recording path reappeared during retention"
                    )
                staged_primary.replace(primary)
            except OSError:
                log.exception(
                    "Retention could not preserve newly referenced item %s", item_id
                )
            return True, 0, True
        cleanup_paths = [staged_primary]
        cleanup_paths.extend(
            self._retention_sidecar_paths(
                primary, category
            )
        )
        freed, cleanup_ok = self._unlink_retention_paths(cleanup_paths)
        if cleanup_ok:
            try:
                cleanup_ok = self.db.finish_retention_deletion(item_id)
            except Exception:
                log.exception(
                    "Retention could not finish deletion journal for item %s",
                    item_id,
                )
                cleanup_ok = False
        if not cleanup_ok:
            log.warning(
                "Retention removed item %s but left recoverable cleanup work",
                item_id,
            )
        return True, freed, not cleanup_ok

    def _archive_usage_bytes(self) -> int:
        total = 0
        for directory, names, filenames in os.walk(
            self.archive_root,
            topdown=True,
            followlinks=False,
        ):
            base = Path(directory)
            names[:] = [name for name in names if not (base / name).is_symlink()]
            for filename in filenames:
                try:
                    info = (base / filename).lstat()
                except OSError:
                    continue
                if stat.S_ISREG(info.st_mode):
                    total += max(0, int(info.st_size))
        return total

    def _vehicle_slug(self, settings: dict[str, Any]) -> str:
        return slugify(settings["vehicle"]["name"])

    def configured_vehicle_identity(self) -> str:
        """Return the stable identity implied by the saved vehicle settings."""
        return self._vehicle_identity(self.db.get_settings())

    @staticmethod
    def _vehicle_connection_fingerprint(settings: dict[str, Any]) -> str:
        vehicle = settings["vehicle"]
        seed = "\0".join(
            (
                str(vehicle.get("base_url") or "").strip().casefold(),
                str(vehicle.get("device_token") or "").strip(),
            )
        )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    @staticmethod
    def _configured_vehicle_identity_is_authoritative(
        settings: dict[str, Any],
    ) -> bool:
        vehicle = settings["vehicle"]
        device_id = str(vehicle.get("device_id") or "").strip()
        if device_id and device_id != "unknown":
            return True
        token = str(vehicle.get("device_token") or "").strip()
        return bool(token and not is_bearer_jwt(token) and "-" in token)

    def can_start_recording_restore(self, restore_identity: str) -> bool:
        """Allow a restore sync when the saved identity matches or needs probing."""
        if not isinstance(restore_identity, str) or not restore_identity:
            return False
        settings = self.db.get_settings()
        fingerprint = self._vehicle_connection_fingerprint(settings)
        with self._state_lock:
            observed_identity = (
                self._observed_vehicle_identity
                if self._observed_vehicle_connection == fingerprint
                else ""
            )
        if observed_identity:
            return restore_identity == observed_identity
        configured_identity = self._vehicle_identity(settings)
        return (
            restore_identity == configured_identity
            or not self._configured_vehicle_identity_is_authoritative(settings)
        )

    def _vehicle_identity(self, settings: dict[str, Any]) -> str:
        vehicle = settings["vehicle"]
        device_id = str(vehicle.get("device_id") or "").strip()
        if device_id and device_id != "unknown":
            seed = f"device-id:{device_id.casefold()}"
        else:
            token = str(vehicle.get("device_token") or "").strip()
            token_prefix = (
                token.rsplit("-", 1)[0].strip()
                if token and not is_bearer_jwt(token) and "-" in token
                else ""
            )
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

    @staticmethod
    def _recording_is_selected(
        item: dict[str, Any],
        selected: set[str],
        selected_severities: set[str],
        include_unknown: bool,
    ) -> bool:
        filename = str(item.get("filename") or "")
        subtype = recording_subtype(item, filename)
        selection_key = recording_selection_key(subtype)
        if selection_key is None:
            if not include_unknown:
                return False
        elif selection_key not in selected:
            return False
        if subtype in {"surveillance", "proximity"} and selected_severities:
            severity = str(item.get("peakSeverity") or "").upper()
            if severity and severity not in selected_severities:
                return False
        return True

    @staticmethod
    def _recording_rows_within_retention(
        rows: list[dict[str, Any]],
        settings: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rule = settings["retention"]["categories"]["recordings"]
        if not rule["enabled"]:
            return rows
        multiplier = {"minutes": 60, "hours": 3600, "days": 86400}[rule["unit"]]
        cutoff_ms = int((time.time() - int(rule["value"]) * multiplier) * 1000)
        protected: set[str] = set()

        def timestamp_for(row: dict[str, Any]) -> int:
            try:
                return max(0, int(row["item"].get("timestamp") or 0))
            except (KeyError, TypeError, ValueError):
                return 0

        if rule["keep_latest_enabled"]:
            ordered = sorted(
                rows,
                key=lambda row: (
                    timestamp_for(row),
                    str(row["source_key"]),
                ),
                reverse=True,
            )
            protected = {
                str(row["source_key"])
                for row in ordered[: int(rule["keep_latest_count"])]
            }
        result: list[dict[str, Any]] = []
        for row in rows:
            timestamp_ms = timestamp_for(row)
            if (
                bool(row.get("restore_requested"))
                or str(row["source_key"]) in protected
                or timestamp_ms == 0
                or timestamp_ms >= cutoff_ms
            ):
                result.append(row)
        return result

    def _recording_archive_path(
        self,
        settings: dict[str, Any],
        item: dict[str, Any],
        *,
        identity: str,
        vehicle: str,
    ) -> tuple[str, str, int, Path, Path]:
        """Return a deterministic destination owned by one source identity."""
        filename = self._safe_filename(item.get("filename"))
        subtype = recording_subtype(item, filename)
        try:
            timestamp_ms = max(0, int(item.get("timestamp") or 0))
        except (TypeError, ValueError) as exc:
            raise OverdriveError("Vehicle returned invalid recording metadata.") from exc
        try:
            date = (
                datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)
                if timestamp_ms > 0
                else datetime.now(timezone.utc)
            )
        except (OSError, OverflowError, ValueError):
            date = datetime.now(timezone.utc)
        relative = (
            Path(settings["destination"]["subdirectory"])
            / vehicle
            / "recordings"
            / subtype
            / f"{date:%Y}"
            / f"{date:%m}"
            / f"{date:%d}"
            / f"{identity}-{timestamp_ms}"
            / filename
        )
        return (
            filename,
            subtype,
            timestamp_ms,
            relative,
            self._safe_archive_path(relative),
        )

    def _discard_vanished_recording_partial(
        self,
        partial_relative_path: Any,
        *,
        source_key: str,
    ) -> bool:
        """Remove only resumable artifacts for a vanished vehicle job."""
        try:
            relative = Path(str(partial_relative_path or ""))
            if (
                len(relative.name) <= len(".part")
                or not relative.name.endswith(".part")
            ):
                raise ValueError("Invalid recording partial path.")
            partial_path = self._retention_safe_path(relative)
        except (OSError, TypeError, ValueError):
            log.warning("Refusing to clean an unsafe vanished recording job")
            return False

        if not source_key.partition(":recording:")[0]:
            return False
        normalized_relative = str(relative)
        try:
            other_references = self._recording_partial_references(
                normalized_relative
            ) - {source_key}
        except (RuntimeError, ValueError):
            return False
        if other_references:
            log.warning(
                "Refusing to clean recording artifacts still referenced by %s",
                ", ".join(sorted(other_references)),
            )
            return False

        paths = (
            partial_path,
            partial_path.with_name(partial_path.name + ".meta"),
            partial_path.with_name(partial_path.name + ".complete.json"),
            partial_path.with_name(
                partial_path.name + ".ownership-conflict.json"
            ),
        )
        for path in paths:
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                return False
            if stat.S_ISDIR(info.st_mode):
                return False
            try:
                # unlink() removes a symlink itself, never the target it names.
                path.unlink()
            except OSError:
                return False
        return True

    @staticmethod
    def _recording_completion_path(partial_path: Path) -> Path:
        return partial_path.with_name(partial_path.name + ".complete.json")

    @staticmethod
    def _recording_conflict_path(partial_path: Path) -> Path:
        return partial_path.with_name(
            partial_path.name + ".ownership-conflict.json"
        )

    def _persist_recording_path_conflict(
        self, partial_path: Path, source_keys: set[str]
    ) -> bool:
        try:
            self._write_json(
                self._recording_conflict_path(partial_path),
                {
                    "version": 1,
                    "source_identities": sorted(source_keys),
                },
            )
        except OSError:
            return False
        return True

    @staticmethod
    def _read_recording_sidecar(path: Path) -> tuple[bool, dict[str, Any] | None]:
        """Read a bounded regular JSON sidecar without following symlinks."""
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False, None
        except OSError:
            return True, None
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024:
            return True, None
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return True, None
        return True, payload if isinstance(payload, dict) else None

    def _recording_shared_path_owner(
        self,
        partial_path: Path,
        source_keys: set[str],
    ) -> str | None:
        """Return the sole sidecar-proven owner, or None for any ambiguity."""
        identities: list[str] = []
        try:
            partial_info = self._path_lstat(partial_path)
        except OSError:
            return None
        meta_exists, meta = self._read_recording_sidecar(
            OverdriveClient._partial_metadata_path(partial_path)
        )
        if meta_exists:
            if (
                meta is None
                or not isinstance(meta.get("source_identity"), str)
                or not isinstance(meta.get("expected_size"), int)
                or isinstance(meta.get("expected_size"), bool)
                or int(meta["expected_size"]) < 0
                or not isinstance(meta.get("total_size"), int)
                or isinstance(meta.get("total_size"), bool)
                or not 0 < int(meta["total_size"]) <= self.max_recording_bytes
                or meta.get("validator_header") not in {"etag", "last-modified"}
                or not isinstance(meta.get("validator_value"), str)
                or not meta.get("validator_value")
            ):
                return None
            if (
                partial_info is None
                or not stat.S_ISREG(partial_info.st_mode)
                or partial_info.st_size > int(meta["total_size"])
            ):
                return None
            identities.append(str(meta["source_identity"]))

        proof_exists, proof = self._read_recording_sidecar(
            self._recording_completion_path(partial_path)
        )
        if proof_exists:
            if (
                proof is None
                or proof.get("version") != 1
                or not isinstance(proof.get("source_identity"), str)
                or not isinstance(proof.get("size"), int)
                or isinstance(proof.get("size"), bool)
                or not 0 < int(proof["size"]) <= self.max_recording_bytes
                or re.fullmatch(
                    r"[0-9a-f]{64}", str(proof.get("sha256") or "").lower()
                )
                is None
            ):
                return None
            final_path = partial_path.with_name(partial_path.name[:-5])
            try:
                final_info = self._path_lstat(final_path)
            except OSError:
                return None
            if final_info is not None:
                # A completion proof authenticates the final object, not a
                # second coexisting .part. Only concordant resume metadata can
                # prove that the latter belongs to the same source.
                if partial_info is not None and not meta_exists:
                    return None
                candidate = final_path
                candidate_info = final_info
            else:
                if partial_info is None:
                    return None
                candidate = partial_path
                candidate_info = partial_info
            try:
                if not stat.S_ISREG(candidate_info.st_mode) or (
                    candidate_info.st_size != int(proof["size"])
                ):
                    return None
                proof_size, proof_digest = self._hash_file(candidate)
            except SyncCancelled:
                raise
            except OSError:
                return None
            if (
                proof_size != int(proof["size"])
                or proof_digest
                != str(proof.get("sha256") or "").lower()
            ):
                return None
            identities.append(str(proof["source_identity"]))

        if not identities or len(set(identities)) != 1:
            return None
        owner = identities[0]
        return owner if owner in source_keys else None

    def _recording_partial_references(
        self,
        partial_relative_path: str,
    ) -> set[str]:
        return self.db.recording_download_job_sources_for_partial(
            partial_relative_path
        )

    def _reroute_recording_job_partial(
        self,
        settings: dict[str, Any],
        *,
        identity: str,
        vehicle: str,
        stored: dict[str, Any],
        blocked_paths: set[str],
    ) -> bool:
        source_key = str(stored.get("source_key") or "")
        item = stored.get("item")
        if not isinstance(item, dict):
            return False
        try:
            filename, _subtype, timestamp_ms, relative, final_path = (
                self._recording_archive_path(
                    settings, item, identity=identity, vehicle=vehicle
                )
            )
            if source_key != f"{identity}:recording:{filename}:{timestamp_ms}":
                return False
            partial = final_path.with_suffix(final_path.suffix + ".part")
            partial_relative = str(partial.relative_to(self.archive_root.resolve()))
            if partial_relative in blocked_paths:
                source_digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()
                final_path = self._safe_archive_path(
                    relative.parent / f"source-{source_digest}" / filename
                )
                partial = final_path.with_suffix(final_path.suffix + ".part")
                partial_relative = str(
                    partial.relative_to(self.archive_root.resolve())
                )
            if partial_relative in blocked_paths:
                return False
            if not self.db.update_recording_download_job_partial_path(
                source_key, partial_relative
            ):
                return False
            blocked_paths.add(partial_relative)
            return True
        except (OSError, TypeError, ValueError, OverdriveError):
            return False

    def _write_recording_completion_proof(
        self,
        partial_path: Path,
        *,
        source_key: str,
        size: int,
        digest: str,
    ) -> None:
        normalized_digest = str(digest).lower()
        if (
            size <= 0
            or size > self.max_recording_bytes
            or re.fullmatch(r"[0-9a-f]{64}", normalized_digest) is None
        ):
            raise OverdriveError(
                "Completed recording verification metadata is invalid."
            )
        try:
            self._write_json(
                self._recording_completion_path(partial_path),
                {
                    "version": 1,
                    "source_identity": source_key,
                    "size": size,
                    "sha256": normalized_digest,
                },
            )
        except OSError as exc:
            raise OverdriveError(
                "Could not persist completed recording verification metadata."
            ) from exc

    def _load_recording_completion_proof(
        self,
        partial_path: Path,
        *,
        source_key: str,
        expected_size: int,
    ) -> tuple[int, str] | None:
        path = self._recording_completion_path(partial_path)
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024:
                return None
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        raw_size = payload.get("size")
        if not isinstance(raw_size, int) or isinstance(raw_size, bool):
            return None
        size = raw_size
        digest = str(payload.get("sha256") or "").lower()
        if (
            payload.get("version") != 1
            or payload.get("source_identity") != source_key
            or size <= 0
            or size > self.max_recording_bytes
            or (expected_size and size != expected_size)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            return None
        return size, digest

    def _inventory_recording_file_is_valid(
        self,
        item: dict[str, Any],
    ) -> bool:
        """Verify that an inventory row still owns the bytes it describes."""
        try:
            if str(item.get("category") or "") != "recordings":
                return False
            path = self._retention_safe_path(item.get("relative_path"))
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                return False
            expected_size = max(0, int(item.get("size_bytes") or 0))
            expected_digest = str(item.get("sha256") or "").lower()
            if (
                info.st_size != expected_size
                or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
            ):
                return False
            size, digest = self._hash_file(path)
            return size == expected_size and digest == expected_digest
        except SyncCancelled:
            raise
        except (OSError, TypeError, ValueError):
            return False

    def _recover_vanished_recording(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        content: dict[str, Any],
        totals: RunTotals,
        *,
        identity: str,
        vehicle: str,
        stored: dict[str, Any],
        partial_relative_path: str,
        policy_check: Callable[[], None],
    ) -> bool:
        """Archive a verified completed transfer before retiring a vanished job.

        A recording can disappear from Overdrive after its last byte was
        downloaded but before the local sidecars and inventory row were
        committed.  The persisted effective ``.part`` path is the recovery
        anchor.  Ambiguous bytes are deliberately retained with the job for a
        later/manual recovery instead of being treated as disposable resume
        data.
        """
        source_key = str(stored.get("source_key") or "")
        item = stored.get("item")
        if not isinstance(item, dict):
            return False
        existing = self.db.get_item_by_source_key(source_key)
        if existing is not None and self._inventory_recording_file_is_valid(existing):
            try:
                self._finalize_recording_restore(source_key)
            except OverdriveError:
                return False
            return self._discard_vanished_recording_partial(
                partial_relative_path, source_key=source_key
            )

        try:
            filename, subtype, timestamp_ms, _canonical_relative, _canonical_path = (
                self._recording_archive_path(
                    settings,
                    item,
                    identity=identity,
                    vehicle=vehicle,
                )
            )
            if source_key != f"{identity}:recording:{filename}:{timestamp_ms}":
                raise ValueError("Stored recording identity is inconsistent.")
            try:
                expected_size = max(0, int(item.get("size") or 0))
            except (TypeError, ValueError) as exc:
                raise ValueError("Stored recording size is invalid.") from exc
            if expected_size > self.max_recording_bytes:
                raise ValueError("Stored recording exceeds the configured size limit.")
            partial_path = self._retention_safe_path(partial_relative_path)
            if (
                len(partial_path.name) <= len(".part")
                or not partial_path.name.endswith(".part")
            ):
                raise ValueError("Stored recording partial path is invalid.")
            final_path = partial_path.with_name(partial_path.name[:-5])
            if final_path.name != filename:
                raise ValueError("Stored recording path does not match its filename.")
            relative = final_path.relative_to(self.archive_root.resolve())
            if self.db.archive_path_has_other_source(str(relative), source_key):
                raise ValueError("Stored recording path belongs to another source.")
        except (OSError, TypeError, ValueError):
            log.warning(
                "Keeping vanished recording job %s because its recovery metadata "
                "or path is invalid",
                source_key,
            )
            return False

        try:
            final_info = final_path.lstat()
        except FileNotFoundError:
            final_info = None
        except OSError:
            return False
        try:
            partial_info = partial_path.lstat()
        except FileNotFoundError:
            partial_info = None
        except OSError:
            return False

        coexisting_final_and_part = (
            final_info is not None and partial_info is not None
        )
        if (
            final_info is not None
            and partial_info is not None
            and not stat.S_ISREG(partial_info.st_mode)
        ):
            self._persist_recording_path_conflict(partial_path, {source_key})
            return False

        if final_info is not None:
            if not stat.S_ISREG(final_info.st_mode):
                return False
            candidate = final_path
            candidate_size = int(final_info.st_size)
        elif partial_info is not None:
            if not stat.S_ISREG(partial_info.st_mode):
                return False
            candidate = partial_path
            candidate_size = int(partial_info.st_size)
        else:
            # A sidecar without bytes cannot be a completed recording.
            return self._discard_vanished_recording_partial(
                partial_relative_path, source_key=source_key
            )

        metadata_path = OverdriveClient._partial_metadata_path(partial_path)
        try:
            metadata_info = metadata_path.lstat()
        except FileNotFoundError:
            metadata_info = None
        except OSError:
            return False
        completion_path = self._recording_completion_path(partial_path)
        try:
            completion_info = completion_path.lstat()
        except FileNotFoundError:
            completion_info = None
        except OSError:
            return False
        if coexisting_final_and_part and completion_info is None:
            self._persist_recording_path_conflict(partial_path, {source_key})
            return False

        # A short deterministic part is known not to be the completed object,
        # even when an interrupted writer left an invalid metadata sidecar.
        if expected_size and candidate_size < expected_size:
            if candidate == partial_path:
                return self._discard_vanished_recording_partial(
                    partial_relative_path, source_key=source_key
                )
            return False
        if expected_size and candidate_size > expected_size:
            return False

        resume_metadata: dict[str, Any] | None = None
        if metadata_info is not None:
            if not stat.S_ISREG(metadata_info.st_mode):
                if coexisting_final_and_part:
                    self._persist_recording_path_conflict(
                        partial_path, {source_key}
                    )
                return False
            resume_metadata = OverdriveClient._load_partial_metadata(
                partial_path,
                source_identity=source_key,
                expected_size=expected_size,
            )
            if resume_metadata is None:
                if coexisting_final_and_part:
                    self._persist_recording_path_conflict(
                        partial_path, {source_key}
                    )
                return False
        elif coexisting_final_and_part:
            self._persist_recording_path_conflict(partial_path, {source_key})
            return False

        completion_proof: tuple[int, str] | None = None
        if completion_info is not None:
            if not stat.S_ISREG(completion_info.st_mode):
                if coexisting_final_and_part:
                    self._persist_recording_path_conflict(
                        partial_path, {source_key}
                    )
                return False
            completion_proof = self._load_recording_completion_proof(
                partial_path,
                source_key=source_key,
                expected_size=expected_size,
            )
            if completion_proof is None:
                if coexisting_final_and_part:
                    self._persist_recording_path_conflict(
                        partial_path, {source_key}
                    )
                return False

        if (
            candidate == partial_path
            and resume_metadata is None
            and completion_proof is None
        ):
            log.warning(
                "Keeping vanished recording job %s because a full .part without "
                "validated transfer metadata cannot prove completion",
                source_key,
            )
            return False

        verified_size = completion_proof[0] if completion_proof else expected_size
        if not verified_size and resume_metadata is not None:
            verified_size = int(resume_metadata["total_size"])
        if verified_size > self.max_recording_bytes:
            log.warning(
                "Keeping vanished recording job %s because its verified size "
                "exceeds the configured recording limit",
                source_key,
            )
            return False
        if not verified_size:
            log.warning(
                "Keeping vanished recording job %s because completion cannot be "
                "proven without a source size or valid resume metadata",
                source_key,
            )
            return False
        if candidate_size < verified_size:
            if candidate == partial_path:
                return self._discard_vanished_recording_partial(
                    partial_relative_path, source_key=source_key
                )
            return False
        if candidate_size != verified_size:
            return False

        try:
            size, digest = self._hash_file(candidate)
        except SyncCancelled:
            raise
        except OSError:
            return False
        if size != verified_size:
            return False
        if completion_proof is not None and digest != completion_proof[1]:
            log.warning(
                "Keeping vanished recording job %s because its SHA-256 does not "
                "match the durable completion proof",
                source_key,
            )
            return False

        if candidate == partial_path:
            try:
                # ``final_path`` was observed missing above. Never overwrite a
                # second local object while recovering the only verified copy.
                if final_path.exists() or final_path.is_symlink():
                    return False
                os.replace(partial_path, final_path)
            except OSError:
                return False
        try:
            os.chmod(final_path, 0o600)
        except OSError:
            pass

        entry = RecordingQueueEntry(
            item=dict(item),
            source_key=source_key,
            filename=filename,
            subtype=subtype,
            timestamp_ms=timestamp_ms,
            expected_size=expected_size,
            relative=relative,
            final_path=final_path,
            partial_path=partial_path,
            existing=existing,
            needs_download=False,
            partial_size=0,
            known_before_run=True,
        )
        try:
            self._inventory_recording(
                client,
                settings,
                content,
                totals,
                vehicle,
                entry,
                size,
                digest,
                policy_check,
            )
        except (PolicyPause, SyncCancelled):
            raise
        except (OSError, OverdriveError) as exc:
            log.warning(
                "Keeping recovered recording %s for an inventory retry: %s",
                filename,
                exc,
            )
            return False

        inventoried = self.db.get_item_by_source_key(source_key)
        if (
            inventoried is None
            or str(inventoried.get("category") or "") != "recordings"
            or str(inventoried.get("relative_path") or "") != str(relative)
            or int(inventoried.get("size_bytes") or -1) != size
            or str(inventoried.get("sha256") or "").lower() != digest
        ):
            return False

        try:
            self._finalize_recording_restore(source_key)
        except OverdriveError:
            return False
        # Resume metadata remains useful proof until inventory is durable.
        # Remove it, and any stale second part, only after that point.
        return self._discard_vanished_recording_partial(
            partial_relative_path, source_key=source_key
        )

    def _build_recording_queue_entry(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        item: dict[str, Any],
        *,
        identity: str,
        vehicle: str,
        known_before_run: bool,
        partial_relative_path: str = "",
    ) -> RecordingQueueEntry:
        filename, subtype, timestamp_ms, relative, final_path = (
            self._recording_archive_path(
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
            )
        )
        canonical_relative = relative
        canonical_final_path = final_path
        try:
            expected_size = max(0, int(item.get("size") or 0))
        except (TypeError, ValueError) as exc:
            raise OverdriveError("Vehicle returned invalid recording metadata.") from exc
        source_key = f"{identity}:recording:{filename}:{timestamp_ms}"
        existing = self.db.get_item_by_source_key(source_key)
        if partial_relative_path:
            stored_partial = self._retention_safe_path(partial_relative_path)
            if (
                len(stored_partial.name) <= len(".part")
                or not stored_partial.name.endswith(".part")
            ):
                raise OverdriveError("Stored recording partial path is invalid.")
            final_path = stored_partial.with_name(stored_partial.name[:-5])
            relative = final_path.relative_to(self.archive_root.resolve())
        if existing is not None:
            try:
                existing_relative = Path(str(existing["relative_path"]))
                final_path = self._safe_archive_path(existing_relative)
                relative = existing_relative
            except (KeyError, OSError, TypeError, ValueError):
                final_path = self._safe_archive_path(relative)
        try:
            if self.db.archive_path_has_other_source(str(relative), source_key):
                # Older builds could assign this path to multiple source keys.
                # Move the current identity to its new canonical destination
                # before any write so the legacy owner's bytes remain intact.
                relative = canonical_relative
                final_path = canonical_final_path
                if self.db.archive_path_has_other_source(
                    str(relative), source_key
                ):
                    source_digest = hashlib.sha256(
                        source_key.encode("utf-8")
                    ).hexdigest()
                    relative = (
                        canonical_relative.parent
                        / f"source-{source_digest}"
                        / filename
                    )
                    final_path = self._safe_archive_path(relative)
                    if self.db.archive_path_has_other_source(
                        str(relative), source_key
                    ):
                        raise OverdriveError(
                            "Recording archive path belongs to another source."
                        )
        except (OSError, TypeError, ValueError) as exc:
            raise OverdriveError(
                "Could not verify recording archive path ownership."
            ) from exc
        partial_path = final_path.with_suffix(final_path.suffix + ".part")
        try:
            effective_partial_relative = str(
                partial_path.relative_to(self.archive_root.resolve())
            )
            path_recorded = self.db.update_recording_download_job_partial_path(
                source_key, effective_partial_relative
            )
        except (OSError, ValueError) as exc:
            raise OverdriveError(
                "Could not persist the recording partial path."
            ) from exc
        if not path_recorded:
            raise OverdriveError("Recording queue job disappeared before transfer.")
        final_path.parent.mkdir(parents=True, exist_ok=True)

        needs_download = not final_path.is_file()
        if not needs_download:
            actual_size = final_path.stat().st_size
            required_size = expected_size
            if not required_size and existing is not None:
                required_size = max(0, int(existing.get("size_bytes") or 0))
            needs_download = bool(required_size and actual_size != required_size)

        partial_size = 0
        if needs_download:
            partial_size = OverdriveClient.resumable_size(
                partial_path,
                source_identity=source_key,
                expected_size=expected_size,
            )

        return RecordingQueueEntry(
            item=dict(item),
            source_key=source_key,
            filename=filename,
            subtype=subtype,
            timestamp_ms=timestamp_ms,
            expected_size=expected_size,
            relative=relative,
            final_path=final_path,
            partial_path=partial_path,
            existing=existing,
            needs_download=needs_download,
            partial_size=partial_size,
            known_before_run=known_before_run,
        )

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
        selected_types = set(content["recording_types"])
        selected_severities = set(content["severities"])
        include_unknown = content["include_unknown_recording_types"]

        self._set_state(stage="discovering", current="Building a fixed recording queue")
        remote_items: list[dict[str, Any]] = []
        seen_filenames: set[str] = set()
        for item in client.iter_recordings([], []):
            self._check_cancelled()
            filename = self._safe_filename(item.get("filename"))
            if filename in seen_filenames:
                raise OverdriveError(
                    "Recordings API returned a duplicate filename."
                )
            seen_filenames.add(filename)
            remote_items.append(dict(item))
        self._check_cancelled()
        all_live_jobs: dict[str, dict[str, Any]] = {}
        all_live_partial_paths: dict[str, str] = {}
        for item in remote_items:
            filename = self._safe_filename(item.get("filename"))
            try:
                timestamp_ms = max(0, int(item.get("timestamp") or 0))
            except (TypeError, ValueError) as exc:
                raise OverdriveError("Vehicle returned invalid recording metadata.") from exc
            source_key = f"{identity}:recording:{filename}:{timestamp_ms}"
            all_live_jobs[source_key] = dict(item)
            _name, _subtype, _timestamp, _relative, final_path = (
                self._recording_archive_path(
                    settings,
                    item,
                    identity=identity,
                    vehicle=vehicle,
                )
            )
            partial_path = final_path.with_suffix(final_path.suffix + ".part")
            all_live_partial_paths[source_key] = str(
                partial_path.relative_to(self.archive_root.resolve())
            )

        # Reconcile deleted-local placeholders only after every API page was
        # fetched successfully. A timeout or partial listing never implies that
        # a recording disappeared from the vehicle.
        self.db.reconcile_recording_tombstones(identity, all_live_jobs)
        live_jobs: dict[str, dict[str, Any]] = {}
        for source_key, item in all_live_jobs.items():
            restore_requested = (
                self.db.recording_restore_requested(source_key)
                and not self.db.recording_retention_cleanup_pending(source_key)
            )
            if restore_requested or (
                not self.db.is_retention_tombstoned(source_key)
                and self._recording_is_selected(
                    item,
                    selected_types,
                    selected_severities,
                    include_unknown,
                )
            ):
                live_jobs[source_key] = dict(item)

        known_live_keys = self.db.remember_recording_download_jobs(
            identity,
            live_jobs,
            {
                source_key: all_live_partial_paths[source_key]
                for source_key in live_jobs
            },
        )
        new_keys = set(live_jobs) - known_live_keys
        persisted_jobs = self.db.list_recording_download_jobs(identity)
        jobs_by_partial: dict[str, list[dict[str, Any]]] = {}
        for stored in persisted_jobs:
            stored_partial = str(stored.get("partial_relative_path") or "")
            if stored_partial:
                jobs_by_partial.setdefault(stored_partial, []).append(stored)

        blocked_paths = set(jobs_by_partial)
        ambiguous_shared_paths: set[str] = set()
        for shared_relative, shared_jobs in jobs_by_partial.items():
            if len(shared_jobs) < 2:
                continue
            source_keys = {str(job["source_key"]) for job in shared_jobs}
            shared_path: Path | None = None
            try:
                shared_path = self._retention_safe_path(shared_relative)
                owner = self._recording_shared_path_owner(
                    shared_path, source_keys
                )
            except (OSError, TypeError, ValueError):
                owner = None

            if owner is None:
                ambiguous_shared_paths.add(shared_relative)
                if shared_path is None or not self._persist_recording_path_conflict(
                    shared_path, source_keys
                ):
                    log.warning(
                        "Keeping ambiguous shared recording path because its "
                        "ownership conflict could not be persisted"
                    )
                    continue

            # A live source that does not provably own legacy shared artifacts
            # must get a fresh source-owned path before download_to can discard
            # or overwrite anything.
            for shared_job in shared_jobs:
                job_key = str(shared_job["source_key"])
                if job_key not in all_live_jobs or job_key == owner:
                    continue
                if not self._reroute_recording_job_partial(
                    settings,
                    identity=identity,
                    vehicle=vehicle,
                    stored=shared_job,
                    blocked_paths=blocked_paths,
                ):
                    log.warning(
                        "Keeping shared recording job %s because a unique path "
                        "could not be persisted",
                        job_key,
                    )

            if owner is None:
                continue

            # Sidecars prove that vanished aliases do not own this artifact.
            # Retire those aliases without touching the owner path.
            for shared_job in shared_jobs:
                job_key = str(shared_job["source_key"])
                if job_key == owner or job_key in all_live_jobs:
                    continue
                existing_alias = self.db.get_item_by_source_key(job_key)
                if (
                    existing_alias is not None
                    and self._inventory_recording_file_is_valid(existing_alias)
                ):
                    try:
                        self._finalize_recording_restore(job_key)
                    except OverdriveError:
                        continue
                self.db.complete_recording_download_job(job_key)

        persisted_jobs = self.db.list_recording_download_jobs(identity)
        shared_after_resolution: dict[str, set[str]] = {}
        for stored in persisted_jobs:
            stored_partial = str(stored.get("partial_relative_path") or "")
            if stored_partial:
                shared_after_resolution.setdefault(stored_partial, set()).add(
                    str(stored["source_key"])
                )
        unresolved_shared_paths = {
            path for path, owners in shared_after_resolution.items() if len(owners) > 1
        }
        unresolved_shared_paths.update(
            path
            for path in ambiguous_shared_paths
            if path in shared_after_resolution
        )
        for path, owners in shared_after_resolution.items():
            if path in unresolved_shared_paths:
                continue
            try:
                partial_path = self._retention_safe_path(path)
                conflict_exists, _conflict = self._read_recording_sidecar(
                    self._recording_conflict_path(partial_path)
                )
                proven_owner = self._recording_shared_path_owner(
                    partial_path, owners
                )
            except (OSError, TypeError, ValueError):
                conflict_exists = True
                proven_owner = None
            if conflict_exists and proven_owner not in owners:
                unresolved_shared_paths.add(path)

        # Recover a source-bound completed live transfer before attempting any
        # new vehicle GET. This covers a crash after the final byte/proof but
        # before rename, sidecars, or inventory.
        for stored in list(persisted_jobs):
            source_key = str(stored["source_key"])
            partial_relative = str(stored.get("partial_relative_path") or "")
            if (
                source_key not in all_live_jobs
                or not partial_relative
                or partial_relative in unresolved_shared_paths
            ):
                continue
            try:
                partial_path = self._retention_safe_path(partial_relative)
                proof_exists, _proof = self._read_recording_sidecar(
                    self._recording_completion_path(partial_path)
                )
                partial_info = self._path_lstat(partial_path)
                final_info = self._path_lstat(
                    partial_path.with_name(partial_path.name[:-5])
                )
                coexisting_final_and_part = (
                    partial_info is not None and final_info is not None
                )
            except (OSError, TypeError, ValueError):
                unresolved_shared_paths.add(partial_relative)
                continue
            if coexisting_final_and_part and not proof_exists:
                self._persist_recording_path_conflict(
                    partial_path, {source_key}
                )
                unresolved_shared_paths.add(partial_relative)
                continue
            if not proof_exists and not coexisting_final_and_part:
                continue
            proven_owner = self._recording_shared_path_owner(
                partial_path, {source_key}
            )
            if proven_owner != source_key:
                self._persist_recording_path_conflict(
                    partial_path, {source_key}
                )
                unresolved_shared_paths.add(partial_relative)
                continue
            if not proof_exists:
                continue
            if self._recover_vanished_recording(
                client,
                settings,
                content,
                totals,
                identity=identity,
                vehicle=vehicle,
                stored=stored,
                partial_relative_path=partial_relative,
                policy_check=policy_check,
            ):
                self.db.complete_recording_download_job(source_key)

        persisted_jobs = self.db.list_recording_download_jobs(identity)
        stored_rows: list[dict[str, Any]] = []
        for stored in persisted_jobs:
            self._check_cancelled()
            source_key = str(stored["source_key"])
            if source_key not in all_live_jobs:
                stored_partial = str(stored.get("partial_relative_path") or "")
                if not stored_partial:
                    _name, _subtype, _timestamp, _relative, final_path = (
                        self._recording_archive_path(
                            settings,
                            stored["item"],
                            identity=identity,
                            vehicle=vehicle,
                        )
                    )
                    stored_partial = str(
                        final_path.with_suffix(final_path.suffix + ".part").relative_to(
                            self.archive_root.resolve()
                        )
                    )
                if stored_partial in unresolved_shared_paths:
                    log.warning(
                        "Keeping vanished recording job %s because its partial "
                        "path has no unique source-bound owner",
                        source_key,
                    )
                    continue
                if not self._recover_vanished_recording(
                    client,
                    settings,
                    content,
                    totals,
                    identity=identity,
                    vehicle=vehicle,
                    stored=stored,
                    partial_relative_path=stored_partial,
                    policy_check=policy_check,
                ):
                    log.warning(
                        "Keeping vanished recording job %s because its local "
                        "artifacts could not be recovered or cleaned safely",
                        source_key,
                    )
                    continue
                self.db.complete_recording_download_job(source_key)
                continue
            if str(stored.get("partial_relative_path") or "") in (
                unresolved_shared_paths
            ):
                log.warning(
                    "Skipping live recording job %s because its shared partial "
                    "path could not be resolved safely",
                    source_key,
                )
                continue
            if self.db.recording_retention_cleanup_pending(source_key):
                # A durable local deletion still owns this source. Preserve any
                # queued restore job, but never write a replacement until its
                # staged primary and sidecars have reached a safe boundary.
                continue
            restore_requested = self.db.recording_restore_requested(source_key)
            if self.db.is_retention_tombstoned(source_key) and not restore_requested:
                self.db.complete_recording_download_job(str(stored["source_key"]))
                continue
            item = stored["item"]
            if not restore_requested and not self._recording_is_selected(
                item,
                selected_types,
                selected_severities,
                include_unknown,
            ):
                continue
            stored["restore_requested"] = restore_requested
            stored_rows.append(stored)

        entries: list[RecordingQueueEntry] = []
        for stored in self._recording_rows_within_retention(stored_rows, settings):
            item = stored["item"]
            entry = self._build_recording_queue_entry(
                client,
                settings,
                item,
                identity=identity,
                vehicle=vehicle,
                known_before_run=str(stored["source_key"]) not in new_keys,
                partial_relative_path=str(
                    stored.get("partial_relative_path") or ""
                ),
            )
            if entry.source_key != str(stored["source_key"]):
                raise OverdriveError("Stored recording queue identity is inconsistent.")
            entries.append(entry)

        downloads = sorted(
            (entry for entry in entries if entry.needs_download),
            key=recording_queue_priority,
        )
        already_local = sorted(
            (entry for entry in entries if not entry.needs_download),
            key=recording_queue_priority,
        )
        progress_by_key = {
            entry.source_key: (entry.partial_size if entry.expected_size else 0)
            for entry in downloads
        }
        known_total = sum(entry.expected_size for entry in downloads if entry.expected_size)
        unknown_sizes = sum(1 for entry in downloads if not entry.expected_size)
        queue_done = sum(progress_by_key.values())
        queue_items_done = 0
        self._set_state(
            stage="queued",
            current=f"{len(downloads)} recording(s) queued",
            queue_bytes_done=queue_done,
            queue_bytes_total=known_total,
            queue_items_done=0,
            queue_items_total=len(downloads),
            queue_unknown_sizes=unknown_sizes,
            queue_bytes_indeterminate=bool(unknown_sizes),
        )

        transfer_failures: list[str] = []
        for entry in downloads:
            self._check_cancelled()
            self._set_state(stage="downloading", current=entry.filename)

            def update_progress(
                current_bytes: int,
                _current_total: int,
                *,
                source_key: str = entry.source_key,
                expected_size: int = entry.expected_size,
            ) -> None:
                nonlocal queue_done
                if not expected_size:
                    return
                bounded = min(expected_size, max(0, int(current_bytes)))
                previous = progress_by_key[source_key]
                if bounded != previous:
                    progress_by_key[source_key] = bounded
                    queue_done += bounded - previous
                    self._set_state(queue_bytes_done=queue_done)

            try:
                self._download_recording_queue_entry(
                    client,
                    settings,
                    content,
                    totals,
                    vehicle,
                    entry,
                    policy_check,
                    update_progress,
                )
            except (PolicyPause, SyncCancelled):
                raise
            except OverdriveError as exc:
                transfer_failures.append(f"{entry.filename}: {exc}")
                log.warning("Recording transfer failed for %s: %s", entry.filename, exc)
                continue
            queue_items_done += 1
            self._set_state(
                queue_items_done=queue_items_done,
                queue_bytes_done=queue_done,
            )
            self._check_cancelled()

        # Existing local files are refreshed after transfer work so thumbnail
        # and metadata backfills cannot delay the frozen download queue.
        for entry in already_local:
            self._check_cancelled()
            size = entry.final_path.stat().st_size
            digest = str((entry.existing or {}).get("sha256") or "")
            if not digest:
                _size, digest = self._hash_file(entry.final_path)
            self._inventory_recording(
                client,
                settings,
                content,
                totals,
                vehicle,
                entry,
                size,
                digest,
                policy_check,
            )
            self._finalize_recording_restore(entry.source_key)
            self._finalize_recording_resume_artifacts(
                entry.partial_path, entry.source_key
            )
            self.db.complete_recording_download_job(entry.source_key)

        if transfer_failures:
            raise OverdriveError(
                f"{len(transfer_failures)} recording(s) remain queued; "
                f"first failure: {transfer_failures[0]}"
            )

    def _finalize_recording_restore(self, source_key: str) -> None:
        if self.db.recording_restore_requested(source_key) and not (
            self.db.complete_recording_restore(source_key)
        ):
            # Keep the download job for a retry instead of exposing a restored
            # item without its retention protection.
            raise OverdriveError(
                "Could not safely finalize the restored recording."
            )

    def _finalize_recording_resume_artifacts(
        self, partial_path: Path, source_key: str
    ) -> None:
        try:
            partial_relative = str(
                partial_path.relative_to(self.archive_root.resolve())
            )
        except ValueError as exc:
            raise OverdriveError(
                "Could not safely finalize recording resume metadata."
            ) from exc
        if not self._discard_vanished_recording_partial(
            partial_relative, source_key=source_key
        ):
            raise OverdriveError(
                "Could not safely finalize recording resume metadata."
            )

    def _download_recording_queue_entry(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        content: dict[str, Any],
        totals: RunTotals,
        vehicle: str,
        entry: RecordingQueueEntry,
        policy_check: Callable[[], None],
        update_progress: Callable[[int, int], None],
    ) -> None:
        size, digest = client.download_to(
            str(
                entry.item.get("videoUrl")
                or f"/video/{client.encoded_filename(entry.filename)}"
            ),
            entry.partial_path,
            max_bytes=self.max_recording_bytes,
            policy_check=policy_check,
            resume=True,
            source_identity=entry.source_key,
            expected_size=entry.expected_size,
            progress_callback=update_progress,
        )
        if entry.expected_size and size != entry.expected_size:
            raise OverdriveError(
                f"Recording size mismatch for {entry.filename}: "
                f"expected {entry.expected_size}, received {size}."
            )
        self._write_recording_completion_proof(
            entry.partial_path,
            source_key=entry.source_key,
            size=size,
            digest=digest,
        )
        update_progress(size, entry.expected_size)
        os.replace(entry.partial_path, entry.final_path)
        try:
            os.chmod(entry.final_path, 0o600)
        except OSError:
            pass
        totals.bytes_added += size
        try:
            self._inventory_recording(
                client,
                settings,
                content,
                totals,
                vehicle,
                entry,
                size,
                digest,
                policy_check,
            )
        except (PolicyPause, SyncCancelled):
            raise
        except OSError as exc:
            raise OverdriveError(
                f"Could not persist archive sidecars for {entry.filename}."
            ) from exc
        self._finalize_recording_restore(entry.source_key)
        self._finalize_recording_resume_artifacts(
            entry.partial_path, entry.source_key
        )
        self.db.complete_recording_download_job(entry.source_key)

    def _inventory_recording(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        content: dict[str, Any],
        totals: RunTotals,
        vehicle: str,
        entry: RecordingQueueEntry,
        size: int,
        digest: str,
        policy_check: Callable[[], None],
    ) -> None:
        """Persist one complete recording as an indivisible queue unit."""
        if content["include_thumbnails"]:
            self._ensure_recording_thumbnail(
                client,
                entry.item,
                entry.final_path,
                policy_check,
            )
        archive_metadata = self._prepare_recording_metadata(
            client,
            entry.item,
            entry.subtype,
            entry.filename,
            entry.final_path,
            settings,
            policy_check,
        )
        if entry.existing is not None:
            if not self.db.update_item(
                source_key=entry.source_key,
                category="recordings",
                subtype=entry.subtype,
                vehicle=vehicle,
                filename=entry.filename,
                relative_path=str(entry.relative),
                media_type="video/mp4",
                size_bytes=size,
                sha256=digest,
                source_timestamp=entry.timestamp_ms or None,
                metadata=archive_metadata,
            ):
                raise OverdriveError(
                    f"Could not refresh the inventory entry for {entry.filename}."
                )
            totals.items_skipped += 1
        elif self.db.add_item(
            source_key=entry.source_key,
            category="recordings",
            subtype=entry.subtype,
            vehicle=vehicle,
            filename=entry.filename,
            relative_path=str(entry.relative),
            media_type="video/mp4",
            size_bytes=size,
            sha256=digest,
            source_timestamp=entry.timestamp_ms or None,
            metadata=archive_metadata,
        ):
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
        policy_check: Callable[[], None],
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
                policy_check,
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
        self._check_cancelled()
        payload = client.fetch_paginated(
            "/api/trips",
            "trips",
            extra_params=range_params,
        )
        self._check_cancelled()
        self._archive_snapshot(settings, totals, "trips", payload)
        return payload

    def _collect_charging(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
    ) -> None:
        self._check_cancelled()
        payload = client.fetch_paginated(
            "/api/charging",
            "sessions",
            extra_params={"days": 0},
        )
        self._check_cancelled()
        self._archive_snapshot(settings, totals, "charging", payload)

    def _collect_simple(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
        category: str,
        path: str,
    ) -> None:
        self._check_cancelled()
        payload = client.get_json(path)
        self._check_cancelled()
        self._archive_snapshot(
            settings,
            totals,
            category,
            payload,
        )

    def _collect_telemetry(
        self,
        client: OverdriveClient,
        settings: dict[str, Any],
        totals: RunTotals,
        trip_cache: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self._check_cancelled()
        current = client.get_json("/api/mqtt/telemetry")
        self._check_cancelled()
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
            self._check_cancelled()
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
            self._check_cancelled()
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
                self._check_cancelled()
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
        self._check_cancelled()
        payload = client.get_json("/api/settings/unified")
        self._check_cancelled()
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
        self._check_cancelled()
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
            self._check_cancelled()
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
        policy_check: Callable[[], None],
    ) -> None:
        if not source_path or destination.exists():
            return
        partial = self._temporary_path(destination)
        try:
            client.download_to(
                source_path,
                partial,
                max_bytes=max_bytes,
                policy_check=policy_check,
            )
            os.replace(partial, destination)
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
        except PolicyPause:
            raise
        except OverdriveError as exc:
            log.info("Optional artifact unavailable: %s", exc)
        finally:
            partial.unlink(missing_ok=True)

    def _ensure_recording_thumbnail(
        self,
        client: OverdriveClient,
        item: dict[str, Any],
        video_path: Path,
        policy_check: Callable[[], None],
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
            policy_check,
        )
        if destination.is_file():
            return
        policy_check()
        self._generate_recording_thumbnail(video_path, destination)
        policy_check()

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
        policy_check: Callable[[], None],
    ) -> dict[str, Any] | None:
        policy_check()
        if destination.exists():
            try:
                if destination.stat().st_size > 32 * 1024 * 1024:
                    return None
                payload = json.loads(destination.read_text(encoding="utf-8"))
                return payload if isinstance(payload, dict) else None
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return None
        partial = self._temporary_path(destination)
        try:
            client.download_to(
                source_path,
                partial,
                max_bytes=32 * 1024 * 1024,
                policy_check=policy_check,
            )
            payload = json.loads(partial.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("optional JSON artifact is not an object")
            os.replace(partial, destination)
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
            policy_check()
            return payload
        except PolicyPause:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, OverdriveError) as exc:
            log.info("Optional JSON artifact unavailable: %s", exc)
            return None
        finally:
            partial.unlink(missing_ok=True)

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
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
        except OSError:
            os.close(descriptor)
            raise
        if not stat.S_ISREG(info.st_mode):
            os.close(descriptor)
            raise OSError("Recording hash source is not a regular file.")
        with os.fdopen(descriptor, "rb") as handle:
            while True:
                self._check_cancelled()
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
