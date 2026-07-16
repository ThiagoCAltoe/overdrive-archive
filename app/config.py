from __future__ import annotations

import copy
import os
import re
from datetime import datetime, time as datetime_time, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CATEGORIES = (
    "recordings",
    "trips",
    "charging",
    "automations",
    "key_mappings",
    "telemetry",
    "roadsense",
    "configuration",
)

RECORDING_TYPES = ("normal", "replay", "sentry", "proximity", "oemDashcam")
SEVERITIES = ("NOTICE", "ALERT", "CRITICAL")
SCHEDULE_MODES = ("manual", "interval", "daily")
INTERVAL_UNITS = ("minutes", "hours", "days")
INTERFACE_LANGUAGES = ("en", "pt-BR")
CAMERA_LAYOUTS = ("standard", "dashcam")

_SUBDIRECTORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class SettingsError(ValueError):
    """Raised when a user-facing setting is invalid."""


def default_settings() -> dict[str, Any]:
    timezone_name = os.environ.get("TZ", "UTC").strip() or "UTC"
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = "UTC"

    return {
        "interface": {
            "language": "en",
        },
        "vehicle": {
            "name": "My vehicle",
            "base_url": "",
            "device_token": "",
            "verify_tls": True,
            "request_timeout_seconds": 30,
            "auto_detect_profile": True,
            "model_id": "",
            "model_name": "",
            "color": "",
            "drive_side": "",
            "device_id": "",
            "app_version": "",
            "locale": "",
            "distance_unit": "",
            "recording_layout": "",
            "surveillance_layout": "",
        },
        "schedule": {
            "enabled": False,
            "mode": "manual",
            "interval_value": 6,
            "interval_unit": "hours",
            "daily_time": "02:00",
            "timezone": timezone_name,
            "only_wifi": True,
            "allowed_ssids": [],
        },
        "content": {
            "categories": [
                "recordings",
                "trips",
                "charging",
                "automations",
                "key_mappings",
                "telemetry",
            ],
            "recording_types": list(RECORDING_TYPES),
            "include_unknown_recording_types": True,
            "severities": list(SEVERITIES),
            "include_thumbnails": True,
            "include_event_timeline": True,
        },
        "destination": {
            "type": "local",
            "subdirectory": (
                os.environ.get("ARCHIVE_DEFAULT_SUBDIRECTORY", "vehicles").strip()
                or "vehicles"
            ),
        },
    }


def _merge(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _string(value: Any, label: str, maximum: int, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise SettingsError(f"{label} must be text.")
    value = value.strip()
    if required and not value:
        raise SettingsError(f"{label} is required.")
    if len(value) > maximum:
        raise SettingsError(f"{label} is too long.")
    return value


def _boolean(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise SettingsError(f"{label} must be true or false.")


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise SettingsError(f"{label} must be a number.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f"{label} must be a number.") from exc
    if parsed < minimum or parsed > maximum:
        raise SettingsError(f"{label} must be between {minimum} and {maximum}.")
    return parsed


def normalize_base_url(value: Any) -> str:
    raw = _string(value, "Vehicle URL", 500)
    if not raw:
        return ""
    if any(char.isspace() or ord(char) < 32 for char in raw):
        raise SettingsError(
            "Vehicle URL must not contain whitespace or control characters."
        )
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise SettingsError("Vehicle URL is invalid.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SettingsError("Vehicle URL must start with http:// or https://.")
    if parsed.username or parsed.password:
        raise SettingsError("Vehicle URL must not contain embedded credentials.")
    if parsed.query or parsed.fragment:
        raise SettingsError("Vehicle URL must not contain a query string or fragment.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SettingsError("Vehicle URL contains an invalid port.") from exc
    if port == 0:
        raise SettingsError("Vehicle URL contains an invalid port.")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def base_url_origin(value: Any) -> tuple[str, str, int] | None:
    normalized = normalize_base_url(value)
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    scheme = parsed.scheme.lower()
    return (
        scheme,
        (parsed.hostname or "").casefold(),
        parsed.port or (443 if scheme == "https" else 80),
    )


def discovered_vehicle_changes(
    current: dict[str, Any],
    discovered: dict[str, Any],
) -> dict[str, str]:
    changes: dict[str, str] = {}
    for key in (
        "device_id",
        "app_version",
        "locale",
        "distance_unit",
        "recording_layout",
        "surveillance_layout",
    ):
        value = str(discovered.get(key) or "").strip()
        if key == "distance_unit":
            value = value.lower()
            if value not in {"km", "mi"}:
                continue
        if key in {"recording_layout", "surveillance_layout"}:
            value = value.lower()
            if value not in CAMERA_LAYOUTS:
                continue
        if value and not (key == "device_id" and value.casefold() == "unknown"):
            changes[key] = value
    for key in ("model_id", "model_name", "color", "drive_side"):
        value = str(discovered.get(key) or "")
        if value and not str(current.get(key) or "").strip():
            changes[key] = value
    return changes


def normalize_subdirectory(value: Any) -> str:
    path = _string(value, "Archive subdirectory", 120, required=True).strip("/")
    if not _SUBDIRECTORY_RE.fullmatch(path):
        raise SettingsError(
            "Archive subdirectory may only contain letters, numbers, dots, dashes, underscores, and slashes."
        )
    if any(part in {"", ".", ".."} for part in path.split("/")):
        raise SettingsError("Archive subdirectory contains an unsafe path segment.")
    return path


def _choice_list(value: Any, allowed: tuple[str, ...], label: str) -> list[str]:
    if not isinstance(value, list):
        raise SettingsError(f"{label} must be a list.")
    result: list[str] = []
    for entry in value:
        if entry not in allowed:
            raise SettingsError(f"Unsupported {label.lower()} value: {entry!r}.")
        if entry not in result:
            result.append(entry)
    return result


def _normalize_ssids(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in re.split(r"[\n,]", value) if part.strip()]
    if not isinstance(value, list):
        raise SettingsError("Allowed Wi-Fi networks must be a list.")
    result: list[str] = []
    for entry in value:
        ssid = _string(entry, "Wi-Fi network name", 64, required=True)
        if ssid not in result:
            result.append(ssid)
    if len(result) > 20:
        raise SettingsError("At most 20 Wi-Fi network names can be configured.")
    return result


def validate_settings(
    candidate: dict[str, Any] | None,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if candidate is None:
        candidate = {}
    if not isinstance(candidate, dict):
        raise SettingsError("Settings payload must be an object.")

    base = current if isinstance(current, dict) else default_settings()
    raw = _merge(base, candidate)

    interface_raw = raw.get("interface")
    vehicle_raw = raw.get("vehicle")
    schedule_raw = raw.get("schedule")
    content_raw = raw.get("content")
    destination_raw = raw.get("destination")
    if not all(
        isinstance(section, dict)
        for section in (
            interface_raw,
            vehicle_raw,
            schedule_raw,
            content_raw,
            destination_raw,
        )
    ):
        raise SettingsError("Settings sections must be objects.")
    assert isinstance(interface_raw, dict)
    assert isinstance(vehicle_raw, dict)
    assert isinstance(schedule_raw, dict)
    assert isinstance(content_raw, dict)
    assert isinstance(destination_raw, dict)

    interface_language = _string(
        interface_raw.get("language"),
        "Interface language",
        10,
        required=True,
    )
    if interface_language not in INTERFACE_LANGUAGES:
        raise SettingsError("Interface language must be en or pt-BR.")
    interface = {
        "language": interface_language,
    }

    vehicle = {
        "name": _string(vehicle_raw.get("name"), "Vehicle name", 80, required=True),
        "base_url": normalize_base_url(vehicle_raw.get("base_url")),
        "device_token": _string(
            vehicle_raw.get("device_token"),
            "Device token or bearer JWT",
            4096,
        ),
        "verify_tls": _boolean(vehicle_raw.get("verify_tls"), "TLS verification"),
        "request_timeout_seconds": _integer(
            vehicle_raw.get("request_timeout_seconds"),
            "Request timeout",
            5,
            180,
        ),
        "auto_detect_profile": _boolean(
            vehicle_raw.get("auto_detect_profile"), "Automatic vehicle discovery"
        ),
        "model_id": _string(vehicle_raw.get("model_id"), "Vehicle model ID", 80),
        "model_name": _string(
            vehicle_raw.get("model_name"), "Vehicle model name", 120
        ),
        "color": _string(vehicle_raw.get("color"), "Vehicle color", 30),
        "drive_side": _string(vehicle_raw.get("drive_side"), "Drive side", 20),
        "device_id": _string(vehicle_raw.get("device_id"), "Device ID", 120),
        "app_version": _string(
            vehicle_raw.get("app_version"), "Overdrive version", 120
        ),
        "locale": _string(vehicle_raw.get("locale"), "Vehicle locale", 30),
        "distance_unit": _string(
            vehicle_raw.get("distance_unit"), "Distance unit", 10
        ),
        "recording_layout": _string(
            vehicle_raw.get("recording_layout"), "Recording camera layout", 20
        ).lower(),
        "surveillance_layout": _string(
            vehicle_raw.get("surveillance_layout"),
            "Surveillance camera layout",
            20,
        ).lower(),
    }
    if vehicle["drive_side"] not in {"", "lhd", "rhd"}:
        raise SettingsError("Drive side must be LHD or RHD.")
    if vehicle["distance_unit"] not in {"", "km", "mi"}:
        raise SettingsError("Distance unit must be km or mi.")
    if vehicle["recording_layout"] not in {"", *CAMERA_LAYOUTS}:
        raise SettingsError("Recording camera layout must be standard or dashcam.")
    if vehicle["surveillance_layout"] not in {"", *CAMERA_LAYOUTS}:
        raise SettingsError(
            "Surveillance camera layout must be standard or dashcam."
        )

    mode = _string(schedule_raw.get("mode"), "Schedule mode", 20, required=True)
    if mode not in SCHEDULE_MODES:
        raise SettingsError("Schedule mode must be manual, interval, or daily.")
    interval_unit = _string(
        schedule_raw.get("interval_unit"), "Interval unit", 20, required=True
    )
    if interval_unit not in INTERVAL_UNITS:
        raise SettingsError("Interval unit must be minutes, hours, or days.")
    daily_time = _string(
        schedule_raw.get("daily_time"), "Daily time", 5, required=True
    )
    if not _TIME_RE.fullmatch(daily_time):
        raise SettingsError("Daily time must use the HH:MM format.")
    timezone_name = _string(
        schedule_raw.get("timezone"), "Timezone", 80, required=True
    )
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise SettingsError("Timezone is not recognized by the container.") from exc

    schedule = {
        "enabled": _boolean(
            schedule_raw.get("enabled"), "Automatic synchronization"
        ),
        "mode": mode,
        "interval_value": _integer(
            schedule_raw.get("interval_value"), "Schedule interval", 1, 10_080
        ),
        "interval_unit": interval_unit,
        "daily_time": daily_time,
        "timezone": timezone_name,
        "only_wifi": _boolean(schedule_raw.get("only_wifi"), "Wi-Fi only"),
        "allowed_ssids": _normalize_ssids(schedule_raw.get("allowed_ssids")),
    }

    content = {
        "categories": _choice_list(
            content_raw.get("categories"), CATEGORIES, "Categories"
        ),
        "recording_types": _choice_list(
            content_raw.get("recording_types"),
            RECORDING_TYPES,
            "Recording types",
        ),
        "include_unknown_recording_types": _boolean(
            content_raw.get("include_unknown_recording_types"),
            "Include new recording types",
        ),
        "severities": _choice_list(
            content_raw.get("severities"), SEVERITIES, "Severities"
        ),
        "include_thumbnails": _boolean(
            content_raw.get("include_thumbnails"), "Include thumbnails"
        ),
        "include_event_timeline": _boolean(
            content_raw.get("include_event_timeline"), "Include event timeline"
        ),
    }

    destination_type = _string(
        destination_raw.get("type"), "Destination type", 20, required=True
    )
    if destination_type != "local":
        raise SettingsError("This release supports the local or mounted-NAS destination.")
    destination = {
        "type": "local",
        "subdirectory": normalize_subdirectory(
            destination_raw.get("subdirectory")
        ),
    }

    return {
        "interface": interface,
        "vehicle": vehicle,
        "schedule": schedule,
        "content": content,
        "destination": destination,
    }


def redact_settings(settings: dict[str, Any]) -> dict[str, Any]:
    redacted = copy.deepcopy(settings)
    token = str(redacted["vehicle"].get("device_token") or "")
    redacted["vehicle"]["device_token"] = ""
    redacted["vehicle"]["device_token_configured"] = bool(token)
    return redacted


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "vehicle"


def interval_seconds(schedule: dict[str, Any]) -> int:
    value = int(schedule["interval_value"])
    multipliers = {"minutes": 60, "hours": 3600, "days": 86400}
    return value * multipliers[schedule["interval_unit"]]


def next_run_at(
    settings: dict[str, Any],
    last_scheduled_at: datetime | None,
    now: datetime | None = None,
) -> datetime | None:
    schedule = settings["schedule"]
    if not schedule["enabled"] or schedule["mode"] == "manual":
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if schedule["mode"] == "interval":
        if last_scheduled_at is None:
            return now
        if last_scheduled_at.tzinfo is None:
            last_scheduled_at = last_scheduled_at.replace(tzinfo=timezone.utc)
        return last_scheduled_at + timedelta(seconds=interval_seconds(schedule))

    local_zone = ZoneInfo(schedule["timezone"])
    local_now = now.astimezone(local_zone)
    hour, minute = (int(part) for part in schedule["daily_time"].split(":", 1))
    candidate = datetime.combine(
        local_now.date(),
        datetime_time(hour=hour, minute=minute),
        tzinfo=local_zone,
    )

    if last_scheduled_at is not None:
        if last_scheduled_at.tzinfo is None:
            last_scheduled_at = last_scheduled_at.replace(tzinfo=timezone.utc)
        last_local = last_scheduled_at.astimezone(local_zone)
        if last_local >= candidate:
            candidate += timedelta(days=1)
        elif candidate <= local_now:
            return now
    elif candidate <= local_now:
        return now

    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def wifi_policy(
    settings: dict[str, Any], network: dict[str, Any] | None
) -> tuple[bool, str]:
    schedule = settings["schedule"]
    if not schedule["only_wifi"]:
        return True, "Wi-Fi restriction is disabled."
    network = network if isinstance(network, dict) else {}
    network_type = str(network.get("type") or "unknown").lower()
    if network_type != "wifi":
        return False, f"Vehicle network is {network_type}; waiting for Wi-Fi."
    allowed = schedule["allowed_ssids"]
    ssid = str(network.get("ssid") or "")
    if allowed and ssid not in allowed:
        return False, "Vehicle Wi-Fi network is not in the allowed SSID list."
    return True, "Vehicle Wi-Fi policy passed."
