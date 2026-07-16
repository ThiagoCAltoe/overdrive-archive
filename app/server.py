from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import secrets
import signal
import shutil
import stat
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__
from .auth import (
    AuthError,
    AuthManager,
    AuthRateLimited,
    normalize_otp_provider,
)
from .config import (
    SettingsError,
    base_url_origin,
    discovered_vehicle_changes,
    redact_settings,
    validate_settings,
)
from .db import Database, RetentionCleanupPending
from .overdrive import OverdriveClient, OverdriveError
from .sync import SyncEngine


log = logging.getLogger("overdrive_archive")
STATIC_ROOT = Path(__file__).resolve().parent / "static"
SESSION_COOKIE = "overdrive_archive_session"
SESSION_TTL = 12 * 60 * 60
MAX_JSON_BODY = 1024 * 1024
REQUEST_SOCKET_TIMEOUT = 30
MAX_LOGIN_USERNAME = 128
MAX_LOGIN_PASSWORD = 1024
MAX_OTP_CODE_INPUT = 16
MAX_SOURCE_KEY_LENGTH = 1000
_MEDIA_ID = re.compile(r"^\d{1,18}$")
_THUMBNAIL_CACHE_CONTROL = "private, max-age=300"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _secret(data_dir: Path) -> bytes:
    path = data_dir / "session.key"
    if path.exists():
        if path.is_symlink():
            raise RuntimeError("Refusing to read a symbolic-link session key.")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise RuntimeError("Session key must be a regular file.")
            try:
                os.fchmod(handle.fileno(), 0o600)
            except OSError:
                pass
            raw = handle.read(4097)
        if len(raw) >= 32:
            return raw
    raw = secrets.token_bytes(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = data_dir / f".session-key-{secrets.token_hex(12)}.part"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return raw


def _prepare_runtime_directories(data_dir: Path, archive_root: Path) -> None:
    archive_was_missing = not archive_root.exists()
    data_dir.mkdir(parents=True, exist_ok=True)
    archive_root.mkdir(parents=True, exist_ok=True)

    try:
        if data_dir.stat().st_uid == os.geteuid():
            os.chmod(data_dir, 0o700)
    except OSError as exc:
        log.warning("Could not normalize permissions for %s: %s", data_dir, exc)

    try:
        archive_stat = archive_root.stat()
        archive_is_owned = archive_stat.st_uid == os.geteuid()
        archive_is_empty_default = bool(
            archive_is_owned
            and stat.S_IMODE(archive_stat.st_mode) == 0o755
            and next(archive_root.iterdir(), None) is None
        )
        if archive_is_owned and (archive_was_missing or archive_is_empty_default):
            os.chmod(archive_root, 0o700)
    except OSError as exc:
        if archive_was_missing:
            log.warning(
                "Could not secure new archive directory %s: %s",
                archive_root,
                exc,
            )
        else:
            log.warning(
                "Could not inspect archive directory permissions for %s: %s",
                archive_root,
                exc,
            )


def _apply_vehicle_token_policy(
    vehicle: dict[str, Any],
    current_vehicle: dict[str, Any],
) -> None:
    vehicle.pop("device_token_configured", None)
    clear_token = vehicle.pop("clear_device_token", False)
    if not isinstance(clear_token, bool):
        raise SettingsError("Clear device token must be true or false.")
    try:
        origin_changed = base_url_origin(
            vehicle.get("base_url", current_vehicle["base_url"])
        ) != base_url_origin(current_vehicle["base_url"])
    except SettingsError:
        origin_changed = False
    supplied_token = vehicle.get("device_token")
    token_is_blank = supplied_token is None or (
        isinstance(supplied_token, str) and not supplied_token.strip()
    )
    if origin_changed:
        for key in ("device_id", "app_version", "locale", "distance_unit"):
            vehicle[key] = ""
    if clear_token or (origin_changed and token_is_blank):
        vehicle["device_token"] = ""
    elif token_is_blank:
        vehicle.pop("device_token", None)
        vehicle["device_token"] = current_vehicle["device_token"]


class ArchiveHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address,
        handler,
        *,
        db: Database,
        engine: SyncEngine,
        archive_root: Path,
        auth: AuthManager,
        secure_cookies: bool,
    ):
        super().__init__(address, handler)
        self.db = db
        self.engine = engine
        self.archive_root = archive_root.resolve()
        self.auth = auth
        self.secure_cookies = secure_cookies

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(REQUEST_SOCKET_TIMEOUT)
        return request, client_address


class Handler(BaseHTTPRequestHandler):
    server: ArchiveHTTPServer
    server_version = "OverdriveArchive"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        path = urlparse(getattr(self, "path", "")).path
        status = str(args[1]) if len(args) > 1 else "-"
        log.info("%s %s %s", self.command, path, status)

    def _headers(
        self,
        content_type: str,
        *,
        cache_control: str = "no-store",
    ) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; img-src 'self' data:; "
            "media-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'",
        )

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        extra_headers: list[tuple[str, str]] | None = None,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self._headers(content_type, cache_control=cache_control)
        for name, value in extra_headers or []:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(
        self,
        status: int,
        payload: dict[str, Any] | list[Any],
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        self._send(
            status,
            body,
            "application/json; charset=utf-8",
            extra_headers=extra_headers,
        )

    def _cookies(self) -> SimpleCookie:
        cookie: SimpleCookie[str] = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            pass
        return cookie

    def _session_token(self) -> str:
        morsel = self._cookies().get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def _authenticated(self) -> bool:
        return self.server.auth.validate_session(self._session_token())

    def _session_cookie(self, token: str, max_age: int = SESSION_TTL) -> str:
        secure = "; Secure" if self.server.secure_cookies else ""
        return (
            f"{SESSION_COOKIE}={token}; Path=/; Max-Age={max_age}; "
            f"HttpOnly; SameSite=Strict{secure}"
        )

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return self.headers.get("Sec-Fetch-Site", "").lower() in {
                "",
                "none",
                "same-origin",
            }
        parsed = urlparse(origin)
        return parsed.netloc.lower() == self.headers.get("Host", "").lower()

    def _read_json(self) -> dict[str, Any] | None:
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != (
            "application/json"
        ):
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_JSON_BODY:
            return None
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError, TimeoutError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    def _require_auth(self) -> bool:
        if self._authenticated():
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"error": "Authentication required."})
        return False

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self._json(200, {"status": "ok", "version": __version__})
            return
        if path in {"/", "/index.html"}:
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            name = path.removeprefix("/static/")
            content_types = {
                "app.css": "text/css; charset=utf-8",
                "app.js": "application/javascript; charset=utf-8",
                "logo.svg": "image/svg+xml",
            }
            if name not in content_types:
                self._json(404, {"error": "Not found."})
                return
            self._serve_static(name, content_types[name])
            return
        if path == "/api/session":
            self._json(
                200,
                {
                    "authenticated": self._authenticated(),
                    "auth": self.server.auth.options(),
                },
            )
            return
        if path == "/api/auth/options":
            self._json(200, self.server.auth.options())
            return
        if path.startswith("/api/"):
            if not self._require_auth():
                return
            self._handle_api_get(path)
            return
        if path.startswith("/media/"):
            if not self._require_auth():
                return
            self._serve_media(path.removeprefix("/media/"))
            return
        if path.startswith("/thumbnail/"):
            if not self._require_auth():
                return
            self._serve_thumbnail(path.removeprefix("/thumbnail/"))
            return
        self._json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._origin_ok():
            self._json(403, {"error": "Cross-origin request rejected."})
            return
        if path == "/api/login":
            self._handle_login()
            return
        if path == "/api/auth/request-code":
            self._handle_request_code()
            return
        if path == "/api/auth/verify-code":
            self._handle_verify_code()
            return
        if not self._require_auth():
            return
        if path == "/api/logout":
            self.server.auth.revoke_session(self._session_token())
            self._json(
                200,
                {"success": True},
                extra_headers=[("Set-Cookie", self._session_cookie("", 0))],
            )
            return
        if path == "/api/sync/stop":
            stopping = self.server.engine.request_stop()
            self._json(
                202 if stopping else 409,
                {
                    "stopping": stopping,
                    "message": (
                        "Synchronization stop requested."
                        if stopping
                        else "No synchronization is running."
                    ),
                },
            )
            return
        if path == "/api/sync":
            started = self.server.engine.trigger("manual")
            self._json(
                202 if started else 409,
                {
                    "started": started,
                    "message": (
                        "Synchronization started."
                        if started
                        else "A synchronization is already running."
                    ),
                },
            )
            return
        if path == "/api/recordings/restore":
            self._handle_recording_restore()
            return
        if path == "/api/recordings/release-retention":
            self._handle_recording_retention_release()
            return
        if path == "/api/test-connection":
            self._handle_test_connection()
            return
        self._json(404, {"error": "Not found."})

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if not self._origin_ok():
            self._json(403, {"error": "Cross-origin request rejected."})
            return
        if not self._require_auth():
            return
        if path == "/api/settings":
            self._handle_settings_update()
            return
        self._json(404, {"error": "Not found."})

    def _serve_static(self, name: str, content_type: str) -> None:
        path = STATIC_ROOT / name
        try:
            body = path.read_bytes()
        except OSError:
            self._json(404, {"error": "Static asset not found."})
            return
        self._send(
            200,
            body,
            content_type,
            cache_control="public, max-age=300",
        )

    def _handle_api_get(self, path: str) -> None:
        if path == "/api/overview":
            storage = self._storage_runtime()
            stats = self.server.db.stats()
            stats.update(storage)
            self._json(
                200,
                {
                    "version": __version__,
                    "stats": stats,
                    "storage": storage,
                    "sync": self.server.engine.state(),
                    "runs": self.server.db.list_runs(8),
                },
            )
            return
        if path == "/api/settings":
            settings = redact_settings(self.server.db.get_settings())
            settings["runtime"] = {
                "archive_root": str(self.server.archive_root),
                "destination_support": ["local"],
                "auth": self.server.auth.options(),
                **self._storage_runtime(),
            }
            self._json(200, settings)
            return
        if path == "/api/runs":
            query = parse_qs(urlparse(self.path).query)
            try:
                limit = int((query.get("limit") or ["50"])[0])
            except ValueError:
                limit = 50
            self._json(200, {"runs": self.server.db.list_runs(limit)})
            return
        if path == "/api/items":
            query = parse_qs(urlparse(self.path).query)
            category = str((query.get("category") or [""])[0])[:40]
            subtype = str((query.get("subtype") or [""])[0])[:40]
            search = str((query.get("q") or [""])[0])[:100]
            try:
                limit = int((query.get("limit") or ["100"])[0])
            except ValueError:
                limit = 100
            limit = max(1, min(limit, 250))
            items = self.server.db.list_items(
                limit=limit,
                category=category,
                subtype=subtype,
                search=search,
            )
            for item in items:
                item["retention_protected"] = bool(
                    item.get("retention_protected")
                )
                item["camera_layout"] = self._camera_layout(item)
                item.pop("metadata_json", None)
                item["thumbnail_url"] = (
                    f"/thumbnail/{item['id']}"
                    if self._thumbnail_path(item) is not None
                    else None
                )
            if category in {"", "recordings"}:
                deleted = self.server.db.list_deleted_recordings(
                    category="recordings",
                    subtype=subtype,
                    search=search,
                    limit=limit,
                )
                items.extend(
                    self._deleted_recording_placeholder(item) for item in deleted
                )
            items.sort(key=self._archive_item_sort_key, reverse=True)
            items = items[:limit]
            self._json(
                200,
                {
                    "items": items,
                    "recording_types": self.server.db.recording_subtypes(),
                },
            )
            return
        self._json(404, {"error": "Not found."})

    @staticmethod
    def _archive_item_sort_key(item: dict[str, Any]) -> tuple[int, str]:
        try:
            timestamp = int(item.get("source_timestamp") or 0)
        except (TypeError, ValueError, OverflowError):
            timestamp = 0
        if 0 < timestamp < 10_000_000_000:
            timestamp *= 1000
        if timestamp <= 0:
            raw = str(item.get("created_at") or item.get("deleted_at") or "")
            try:
                parsed = datetime.fromisoformat(raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamp = int(parsed.timestamp() * 1000)
            except (OSError, OverflowError, ValueError):
                timestamp = 0
        return timestamp, str(item.get("filename") or "")

    @staticmethod
    def _deleted_recording_placeholder(item: dict[str, Any]) -> dict[str, Any]:
        """Expose only the metadata needed to identify and restore a deleted clip."""
        deleted_at = str(item.get("deleted_at") or "")
        restore_requested_at = str(item.get("restore_requested_at") or "")
        cleanup_pending = bool(item.get("cleanup_pending"))
        return {
            "id": None,
            "category": "recordings",
            "subtype": str(item.get("subtype") or "")[:40],
            "vehicle": str(item.get("vehicle") or ""),
            "filename": str(item.get("filename") or ""),
            "source_timestamp": item.get("source_timestamp"),
            "created_at": deleted_at,
            "deleted_at": deleted_at,
            "last_seen_at": str(item.get("last_seen_at") or ""),
            "restore_requested_at": restore_requested_at,
            "restore_requested": bool(restore_requested_at),
            "cleanup_pending": cleanup_pending,
            "source_key": str(item.get("source_key") or ""),
            "deleted_local": True,
            "size_bytes": 0,
            "remote_size_bytes": max(
                0, int(item.get("remote_size_bytes") or 0)
            ),
            "retention_protected": False,
            "media_type": "",
            "camera_layout": None,
            "thumbnail_url": None,
            "media_url": None,
        }

    def _storage_runtime(self) -> dict[str, int]:
        try:
            usage = shutil.disk_usage(self.server.archive_root)
        except OSError:
            return {
                "storage_capacity_bytes": 0,
                "storage_free_bytes": 0,
                "storage_used_bytes": 0,
            }
        return {
            "storage_capacity_bytes": max(0, int(usage.total)),
            "storage_free_bytes": max(0, int(usage.free)),
            "storage_used_bytes": max(0, int(usage.used)),
        }

    def _handle_login(self) -> None:
        payload = self._read_json()
        if payload is None:
            self._json(400, {"error": "A JSON login payload is required."})
            return
        username_value = payload.get("username")
        password_value = payload.get("password")
        username = username_value if isinstance(username_value, str) else ""
        password = password_value if isinstance(password_value, str) else ""
        if len(username) > MAX_LOGIN_USERNAME or len(password) > MAX_LOGIN_PASSWORD:
            self._json(401, {"error": "Invalid username or password."})
            return
        try:
            result = self.server.auth.authenticate_local(
                username,
                password,
                self.client_address[0],
            )
        except AuthRateLimited as exc:
            self._json(
                429,
                {"error": str(exc), "retry_after": exc.retry_after},
                extra_headers=[("Retry-After", str(exc.retry_after))],
            )
            return
        except AuthError as exc:
            self._json(401, {"error": str(exc)})
            return
        self._json(
            200,
            {"success": True, "method": result.method},
            extra_headers=[
                ("Set-Cookie", self._session_cookie(result.token))
            ],
        )

    def _handle_request_code(self) -> None:
        payload = self._read_json()
        try:
            provider = normalize_otp_provider((payload or {}).get("provider"))
        except AuthError as exc:
            self._json(400, {"error": str(exc)})
            return
        try:
            self.server.auth.request_otp(provider, self.client_address[0])
        except AuthRateLimited as exc:
            self._json(
                429,
                {"error": str(exc), "retry_after": exc.retry_after},
                extra_headers=[("Retry-After", str(exc.retry_after))],
            )
            return
        except AuthError as exc:
            log.warning(
                "OTP request failed for configured provider %s: %s",
                provider,
                exc,
            )
            self._json(
                503,
                {
                    "error": (
                        "The sign-in code could not be sent. "
                        "Check the configured provider."
                    )
                },
            )
            return
        self._json(
            202,
            {
                "success": True,
                "message": "If the provider is configured, a one-time code was sent.",
            },
        )

    def _handle_verify_code(self) -> None:
        payload = self._read_json()
        try:
            provider = normalize_otp_provider((payload or {}).get("provider"))
        except AuthError as exc:
            self._json(400, {"error": str(exc)})
            return
        raw_code = (payload or {}).get("code")
        code = (
            raw_code.replace(" ", "")
            if isinstance(raw_code, str) and len(raw_code) <= MAX_OTP_CODE_INPUT
            else ""
        )
        try:
            result = self.server.auth.verify_otp(
                provider,
                code,
                self.client_address[0],
            )
        except AuthRateLimited as exc:
            self._json(
                429,
                {"error": str(exc), "retry_after": exc.retry_after},
                extra_headers=[("Retry-After", str(exc.retry_after))],
            )
            return
        except AuthError as exc:
            self._json(401, {"error": str(exc)})
            return
        self._json(
            200,
            {"success": True, "method": result.method},
            extra_headers=[
                ("Set-Cookie", self._session_cookie(result.token))
            ],
        )

    def _handle_settings_update(self) -> None:
        payload = self._read_json()
        if payload is None:
            self._json(400, {"error": "A JSON settings object is required."})
            return
        current = self.server.db.get_settings()
        vehicle = payload.get("vehicle")
        try:
            if isinstance(vehicle, dict):
                _apply_vehicle_token_policy(vehicle, current["vehicle"])
            normalized = validate_settings(payload, current)
            storage_limit = normalized["retention"]["storage_limit"]
            capacity = self._storage_runtime()["storage_capacity_bytes"]
            if (
                storage_limit["enabled"]
                and capacity > 0
                and storage_limit["max_bytes"] > capacity
            ):
                raise SettingsError(
                    "Storage limit cannot exceed the archive filesystem capacity."
                )
            saved = self.server.db.save_settings(payload)
        except SettingsError as exc:
            self._json(400, {"error": str(exc)})
            return
        retention_result = self.server.engine.apply_retention(saved)
        self._json(
            200,
            {
                "success": True,
                "settings": redact_settings(saved),
                "retention": retention_result,
            },
        )

    def _handle_recording_restore(self) -> None:
        payload = self._read_json()
        source_key = payload.get("source_key") if isinstance(payload, dict) else None
        if (
            not isinstance(source_key, str)
            or not source_key.strip()
            or len(source_key.strip()) > MAX_SOURCE_KEY_LENGTH
            or any(ord(character) < 32 for character in source_key)
        ):
            self._json(400, {"error": "A valid source_key is required."})
            return
        source_key = source_key.strip()
        try:
            restore_identity = self.server.db.request_recording_restore(source_key)
        except RetentionCleanupPending:
            self._json(
                409,
                {
                    "error": (
                        "Local retention cleanup is still in progress. "
                        "Try again shortly."
                    ),
                    "code": "retention_cleanup_pending",
                },
            )
            return
        except ValueError:
            self._json(400, {"error": "A valid source_key is required."})
            return
        if not restore_identity:
            self._json(404, {"error": "Deleted recording not found."})
            return
        sync_started = bool(
            self.server.engine.can_start_recording_restore(restore_identity)
            and self.server.engine.trigger("restore")
        )
        self._json(
            202,
            {
                "queued": True,
                "sync_started": sync_started,
            },
        )

    def _handle_recording_retention_release(self) -> None:
        payload = self._read_json()
        item_id = payload.get("item_id") if isinstance(payload, dict) else None
        if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id <= 0:
            self._json(400, {"error": "A valid item_id is required."})
            return
        item = self.server.db.get_item(item_id)
        if not item or item.get("category") != "recordings":
            self._json(404, {"error": "Archived recording not found."})
            return
        source_key = str(item.get("source_key") or "")
        if not self.server.db.clear_retention_protection(source_key):
            self._json(409, {"error": "Recording is not protected from retention."})
            return
        retention = self.server.engine.apply_retention(
            self.server.db.get_settings()
        )
        self._json(
            200,
            {
                "released": True,
                "item_deleted": self.server.db.get_item(item_id) is None,
                "retention": retention,
            },
        )

    def _handle_test_connection(self) -> None:
        settings = self.server.db.get_settings()
        vehicle = settings["vehicle"]
        try:
            client = OverdriveClient(
                base_url=vehicle["base_url"],
                device_token=vehicle["device_token"],
                verify_tls=vehicle["verify_tls"],
                timeout=vehicle["request_timeout_seconds"],
            )
            status = client.status()
            profile = client.discover_vehicle_profile(status)
            if settings["vehicle"].get("auto_detect_profile"):
                discovered = discovered_vehicle_changes(
                    settings["vehicle"],
                    profile,
                )
                if discovered:
                    settings = self.server.db.save_settings(
                        {"vehicle": discovered}
                    )
            network = status.get("network")
            if not isinstance(network, dict):
                network = {}
            self._json(
                200,
                {
                    "success": True,
                    "network": {
                        "type": network.get("type") or "unknown",
                        "ssid": network.get("ssid") or "",
                        "signal": network.get("signal"),
                    },
                    "profile": profile,
                    "settings": redact_settings(settings),
                },
            )
        except OverdriveError as exc:
            self._json(502, {"success": False, "error": str(exc)})

    @staticmethod
    def _camera_layout(item: dict[str, Any]) -> str | None:
        if item.get("category") != "recordings":
            return None
        if item.get("subtype") == "oem_dashcam":
            return "single"
        metadata: dict[str, Any] = {}
        raw_metadata = item.get("metadata_json")
        if isinstance(raw_metadata, str):
            try:
                parsed = json.loads(raw_metadata)
                if isinstance(parsed, dict):
                    metadata = parsed
            except (json.JSONDecodeError, TypeError):
                pass
        for key in (
            "archiveCameraLayout",
            "cameraLayout",
            "recordingLayout",
            "layout",
        ):
            layout = str(metadata.get(key) or "").strip().lower()
            if layout in {"standard", "dashcam", "single"}:
                return layout
        if item.get("subtype") in {
            "drive",
            "replay",
            "surveillance",
            "proximity",
        }:
            return "standard"
        return "single"

    def _thumbnail_path(self, item: dict[str, Any]) -> Path | None:
        if item.get("category") != "recordings":
            return None
        relative_value = item.get("relative_path")
        if not isinstance(relative_value, str) or not relative_value:
            return None
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        try:
            path = (
                self.server.archive_root / relative
            ).with_suffix(".jpg").resolve(strict=True)
            path.relative_to(self.server.archive_root)
            if not path.is_file():
                return None
        except (OSError, ValueError):
            return None
        return path

    def _serve_thumbnail(self, raw_id: str) -> None:
        if not _MEDIA_ID.fullmatch(raw_id):
            self._json(404, {"error": "Thumbnail not found."})
            return
        item = self.server.db.get_item(int(raw_id))
        path = self._thumbnail_path(item) if item else None
        if path is None:
            self._json(404, {"error": "Thumbnail not found."})
            return
        try:
            body = path.read_bytes()
        except OSError:
            self._json(404, {"error": "Thumbnail not found."})
            return
        self._send(
            200,
            body,
            "image/jpeg",
            cache_control=_THUMBNAIL_CACHE_CONTROL,
        )

    def _serve_media(self, raw_id: str) -> None:
        if not _MEDIA_ID.fullmatch(raw_id):
            self._json(404, {"error": "Archive item not found."})
            return
        item = self.server.db.get_item(int(raw_id))
        if not item:
            self._json(404, {"error": "Archive item not found."})
            return
        try:
            path = (self.server.archive_root / item["relative_path"]).resolve(strict=True)
            path.relative_to(self.server.archive_root)
            if not path.is_file():
                raise OSError("not a file")
            stat = path.stat()
        except (OSError, ValueError):
            self._json(404, {"error": "Archived file is missing."})
            return

        start = 0
        end = stat.st_size - 1
        status = 200
        range_header = self.headers.get("Range", "")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or (not match.group(1) and not match.group(2)):
                self._range_error(stat.st_size)
                return
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else end
            else:
                suffix = int(match.group(2))
                start = max(0, stat.st_size - suffix)
            end = min(end, stat.st_size - 1)
            if start < 0 or start > end or start >= stat.st_size:
                self._range_error(stat.st_size)
                return
            status = 206

        length = end - start + 1
        content_type = str(item.get("media_type") or "")
        if not content_type:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        disposition = "inline" if content_type.startswith(("video/", "image/", "text/")) else "attachment"
        clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", path.name)

        self.send_response(status)
        self._headers(content_type, cache_control="private, max-age=300")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header(
            "Content-Disposition",
            f'{disposition}; filename="{clean_name}"',
        )
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{stat.st_size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def _range_error(self, size: int) -> None:
        self.send_response(416)
        self._headers("application/json; charset=utf-8")
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self.end_headers()


def main() -> None:
    os.umask(0o077)
    level = os.environ.get("ARCHIVE_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.environ.get("ARCHIVE_HOST", "127.0.0.1")
    port = int(os.environ.get("ARCHIVE_PORT", "8080"))
    data_dir = Path(os.environ.get("ARCHIVE_DATA_DIR", "/data")).resolve()
    archive_root = Path(os.environ.get("ARCHIVE_ROOT", "/archive")).resolve()
    _prepare_runtime_directories(data_dir, archive_root)

    try:
        db = Database(data_dir / "archive.sqlite3")
        session_secret = _secret(data_dir)
        auth = AuthManager(db, session_secret)
    except (AuthError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    engine = SyncEngine(db, archive_root)
    engine.start_scheduler()
    server = ArchiveHTTPServer(
        (host, port),
        Handler,
        db=db,
        engine=engine,
        archive_root=archive_root,
        auth=auth,
        secure_cookies=_bool_env("ARCHIVE_SECURE_COOKIES"),
    )

    def stop_server(signum, frame) -> None:
        log.info("Stopping after signal %s", signum)
        engine.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    log.info("Overdrive Archive %s listening on %s:%s", __version__, host, port)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        engine.stop()
        server.server_close()
