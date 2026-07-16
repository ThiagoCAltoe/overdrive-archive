from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import ssl
import stat
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
    HTTPSHandler,
)


class OverdriveError(RuntimeError):
    """A safe, user-facing connector error."""


_JWT_RE = re.compile(
    r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$"
)
_CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


def is_bearer_jwt(value: str) -> bool:
    return bool(value and len(value) <= 4096 and _JWT_RE.fullmatch(value))


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved = urljoin(req.full_url, newurl)
        old = urlsplit(req.full_url)
        new = urlsplit(resolved)
        old_port = old.port or (443 if old.scheme == "https" else 80)
        new_port = new.port or (443 if new.scheme == "https" else 80)
        if (old.scheme, old.hostname, old_port) != (
            new.scheme,
            new.hostname,
            new_port,
        ):
            raise HTTPError(
                req.full_url,
                code,
                "Cross-origin redirect blocked",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, resolved)


class OverdriveClient:
    def __init__(
        self,
        *,
        base_url: str,
        device_token: str,
        verify_tls: bool = True,
        timeout: int = 30,
        user_agent: str = "Overdrive-Archive/0.1",
    ):
        self.base_url = base_url.rstrip("/")
        self.device_token = device_token.strip()
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.user_agent = user_agent
        self.jwt = ""

        context = ssl.create_default_context()
        if not verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self.opener = build_opener(
            _SameOriginRedirectHandler(),
            HTTPSHandler(context=context),
        )

    def _url(self, path: str) -> str:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        expected = urlsplit(self.base_url)
        actual = urlsplit(url)
        expected_port = expected.port or (443 if expected.scheme == "https" else 80)
        actual_port = actual.port or (443 if actual.scheme == "https" else 80)
        if (expected.scheme, expected.hostname, expected_port) != (
            actual.scheme,
            actual.hostname,
            actual_port,
        ):
            raise OverdriveError("Connector refused a URL outside the configured vehicle.")
        return url

    def _open(
        self,
        path: str,
        *,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
        request_headers: dict[str, str] | None = None,
    ):
        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "Connection": "close",
        }
        if json_body is not None:
            data = json.dumps(json_body, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        if authenticated:
            if not self.jwt:
                self.authenticate()
            headers["Authorization"] = f"Bearer {self.jwt}"
        for header in ("Range", "If-Range"):
            value = str((request_headers or {}).get(header) or "").strip()
            if value:
                headers[header] = value
        request = Request(
            self._url(path),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            return self.opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            if exc.code == 401 and authenticated:
                self.jwt = ""
            if exc.code == 401:
                message = "Overdrive authentication failed (HTTP 401)."
            elif exc.code == 403:
                message = "Overdrive refused access (HTTP 403)."
            elif exc.code == 404:
                message = "The requested Overdrive API is unavailable (HTTP 404)."
            else:
                message = f"Overdrive returned HTTP {exc.code}."
            raise OverdriveError(message) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OverdriveError(
                "Could not reach the vehicle. Check its URL, network, VPN, "
                "and availability."
            ) from exc

    def authenticate(self) -> None:
        if not self.base_url:
            raise OverdriveError("Vehicle URL is not configured.")
        if not self.device_token:
            raise OverdriveError("Overdrive device token is not configured.")

        token = self.device_token
        if is_bearer_jwt(token):
            self.jwt = token
            return
        if len(token) == 8 and "-" not in token:
            status = self.get_json("/auth/status", authenticated=False)
            device_id = str(status.get("deviceId") or "").strip()
            if not device_id or device_id == "unknown":
                raise OverdriveError(
                    "Could not discover the device ID. Enter the full device token."
                )
            token = f"{device_id}-{token.lower()}"

        payload = self.get_json(
            "/auth/token",
            method="POST",
            json_body={"token": token},
            authenticated=False,
        )
        jwt = str(payload.get("jwt") or "")
        if not payload.get("success") or not jwt:
            raise OverdriveError(str(payload.get("error") or "Vehicle authentication failed."))
        self.jwt = jwt

    def get_json(
        self,
        path: str,
        *,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
        max_bytes: int = 32 * 1024 * 1024,
    ) -> dict[str, Any]:
        with self._open(
            path,
            method=method,
            json_body=json_body,
            authenticated=authenticated,
        ) as response:
            raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise OverdriveError("Vehicle JSON response exceeded the safety limit.")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OverdriveError("Vehicle returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise OverdriveError("Vehicle returned an unexpected JSON response.")
        return payload

    def status(self) -> dict[str, Any]:
        return self.get_json("/status")

    def discover_vehicle_profile(
        self, status: dict[str, Any] | None = None
    ) -> dict[str, str]:
        status = status if isinstance(status, dict) else self.status()
        profile = {
            "device_id": str(status.get("deviceId") or ""),
            "app_version": str(status.get("appVersion") or ""),
            "locale": str(status.get("locale") or ""),
            "distance_unit": str(status.get("distanceUnit") or ""),
            "model_id": "",
            "model_name": "",
            "color": "",
            "drive_side": "",
            "recording_layout": "",
            "surveillance_layout": "",
        }
        try:
            selected = self.get_json("/api/models/selected")
            profile["model_id"] = str(selected.get("modelId") or "")
            profile["color"] = str(selected.get("color") or "")
            drive_side = str(selected.get("driveSide") or "").lower()
            profile["drive_side"] = drive_side if drive_side in {"lhd", "rhd"} else ""
        except OverdriveError:
            pass

        for profile_key, endpoint in (
            ("recording_layout", "/api/settings/recording-layout"),
            ("surveillance_layout", "/api/settings/surveillance-layout"),
        ):
            try:
                layout_payload = self.get_json(endpoint)
                layout = str(layout_payload.get("layout") or "").strip().lower()
                if layout in {"standard", "dashcam"}:
                    profile[profile_key] = layout
            except OverdriveError:
                pass

        try:
            listing = self.get_json("/api/models/list")
            models = listing.get("models")
            if isinstance(models, list):
                for model in models:
                    if (
                        isinstance(model, dict)
                        and str(model.get("id") or "") == profile["model_id"]
                    ):
                        profile["model_name"] = str(
                            model.get("name") or profile["model_id"]
                        )
                        break
        except OverdriveError:
            pass
        if not profile["model_name"] and profile["model_id"]:
            profile["model_name"] = profile["model_id"].replace("-", " ").title()
        return profile

    def iter_recordings(
        self,
        recording_types: list[str],
        severities: list[str],
    ) -> Iterator[dict[str, Any]]:
        requested_page_size = 200
        page_size: int | None = None
        listing_total: int | None = None
        emitted = 0
        for page in range(1, 1001):
            request_page_size = page_size or requested_page_size
            params: dict[str, Any] = {
                "page": page,
                "pageSize": request_page_size,
            }
            if recording_types:
                params["type"] = ",".join(recording_types)
            if severities:
                params["severity"] = ",".join(severities)
            payload = self.get_json(f"/api/recordings?{urlencode(params)}")
            if payload.get("warming") or payload.get("reconciling"):
                raise OverdriveError(
                    "The recording index is still being built. Try the sync again shortly."
                )
            recordings = payload.get("recordings")
            if not isinstance(recordings, list):
                raise OverdriveError("Recordings API returned an unexpected response.")
            try:
                total_count = int(payload["totalCount"])
                total_pages = int(payload["totalPages"])
                response_page = int(payload["page"])
                response_page_size = int(payload["pageSize"])
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise OverdriveError(
                    "Recordings API returned invalid pagination metadata."
                ) from exc
            if page_size is None:
                # Older Overdrive releases clamp the requested 200 rows to a
                # smaller server-side maximum. Adopt the value reported by the
                # first response and use it for every following request so page
                # offsets cannot overlap or leave gaps.
                if not 1 <= response_page_size <= requested_page_size:
                    raise OverdriveError(
                        "Recordings API returned inconsistent pagination metadata."
                    )
                page_size = response_page_size
            expected_pages = max(1, (total_count + page_size - 1) // page_size)
            if (
                total_count < 0
                or total_pages != expected_pages
                or total_pages > 1000
                or response_page != page
                or response_page_size != page_size
            ):
                raise OverdriveError(
                    "Recordings API returned inconsistent pagination metadata."
                )
            if listing_total is None:
                listing_total = total_count
            elif listing_total != total_count:
                raise OverdriveError(
                    "The recording listing changed while it was being read."
                )
            expected_items = min(
                page_size,
                max(0, total_count - (page - 1) * page_size),
            )
            if len(recordings) != expected_items or not all(
                isinstance(item, dict) for item in recordings
            ):
                raise OverdriveError(
                    "Recordings API returned an incomplete page."
                )
            for item in recordings:
                emitted += 1
                yield item
            if page >= total_pages:
                if emitted != total_count:
                    raise OverdriveError(
                        "Recordings API returned an incomplete listing."
                    )
                return
        raise OverdriveError(
            "The recording listing exceeded the safe pagination limit."
        )

    def fetch_paginated(
        self,
        path: str,
        array_key: str,
        *,
        limit: int = 200,
        max_pages: int = 100,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        offset = 0
        items: list[Any] = []
        last_payload: dict[str, Any] = {}
        for _ in range(max_pages):
            params = dict(extra_params or {})
            params.update({"limit": limit, "offset": offset})
            separator = "&" if "?" in path else "?"
            payload = self.get_json(f"{path}{separator}{urlencode(params)}")
            page_items = payload.get(array_key)
            if not isinstance(page_items, list):
                raise OverdriveError(
                    f"Vehicle response did not contain a {array_key!r} list."
                )
            items.extend(page_items)
            last_payload = payload
            if len(page_items) < limit:
                break
            offset += len(page_items)
        result = dict(last_payload)
        result[array_key] = items
        result["archivedCount"] = len(items)
        return result

    def download_to(
        self,
        path: str,
        destination: Path,
        *,
        max_bytes: int,
        policy_check: Callable[[], None] | None = None,
        resume: bool = False,
        source_identity: str = "",
        expected_size: int = 0,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[int, str]:
        """Download a file, optionally resuming a validated deterministic part.

        Resume data is accepted only when its sidecar matches the source and the
        server supplies a stable ETag or Last-Modified validator.  A server that
        ignores Range safely restarts the transfer from byte zero.
        """
        expected = max(0, int(expected_size))
        identity = str(source_identity or path)
        metadata_path = self._partial_metadata_path(destination)
        existing = 0
        metadata: dict[str, Any] | None = None

        if resume:
            metadata = self._load_partial_metadata(
                destination,
                source_identity=identity,
                expected_size=expected,
            )
            existing = self.resumable_size(
                destination,
                source_identity=identity,
                expected_size=expected,
            )
            if destination.exists() and not existing:
                self._discard_partial(destination)
                metadata = None
        elif destination.exists() or metadata_path.exists():
            raise OverdriveError("Could not create a private temporary download file.")

        if existing > max_bytes:
            self._discard_partial(destination)
            raise OverdriveError("Recording exceeded the configured size limit.")
        completed_total = expected
        if not completed_total and metadata is not None:
            completed_total = int(metadata["total_size"])
        if completed_total and existing == completed_total:
            if policy_check:
                policy_check()
            size, digest_hex = self._hash_download(destination, policy_check)
            if progress_callback:
                progress_callback(size, completed_total)
            return size, digest_hex

        request_headers: dict[str, str] = {}
        if existing and metadata is not None:
            request_headers["Range"] = f"bytes={existing}-"
            request_headers["If-Range"] = str(metadata["validator_value"])
        if policy_check:
            policy_check()

        response = (
            self._open(path, request_headers=request_headers)
            if request_headers
            else self._open(path)
        )
        with response:
            status = self._response_status(response)
            headers = self._response_headers(response)
            content_length = self._header_int(headers, "content-length")
            target_total = expected
            append = False

            if existing and status == 206:
                if metadata is None:
                    self._discard_partial(destination)
                    raise OverdriveError(
                        "Resumable recording metadata is unavailable."
                    )
                parsed_range = self._parse_content_range(headers.get("content-range", ""))
                if (
                    parsed_range is None
                    or parsed_range[0] != existing
                    or parsed_range[1] < parsed_range[0]
                    or parsed_range[2] != int(metadata["total_size"])
                    or (expected and parsed_range[2] != expected)
                    or not self._validator_matches(metadata, headers)
                ):
                    self._discard_partial(destination)
                    raise OverdriveError("Vehicle returned an invalid resumed recording range.")
                declared = parsed_range[1] - parsed_range[0] + 1
                if content_length is not None and content_length != declared:
                    self._discard_partial(destination)
                    raise OverdriveError("Vehicle returned an inconsistent resumed recording size.")
                target_total = parsed_range[2]
                if target_total > max_bytes:
                    raise OverdriveError("Recording exceeded the configured size limit.")
                append = True
            elif existing:
                # If-Range deliberately permits a full 200 response when the
                # remote object changed.  Discard the stale prefix and restart.
                self._discard_partial(destination)
                existing = 0
                metadata = None

            if not append:
                if status not in (200, 206):
                    raise OverdriveError("Vehicle returned an unexpected download response.")
                if status == 206:
                    parsed_range = self._parse_content_range(headers.get("content-range", ""))
                    if parsed_range is None or parsed_range[0] != 0:
                        raise OverdriveError("Vehicle returned an invalid recording range.")
                    target_total = parsed_range[2]
                elif not target_total and content_length is not None:
                    target_total = content_length
                if expected and content_length is not None and content_length != expected:
                    raise OverdriveError(
                        "Vehicle reported a recording size that differs from its index."
                    )
                if target_total > max_bytes:
                    raise OverdriveError("Recording exceeded the configured size limit.")

                validator = self._select_validator(headers)
                if resume and validator and target_total:
                    self._write_partial_metadata(
                        metadata_path,
                        source_identity=identity,
                        expected_size=expected,
                        total_size=target_total,
                        validator=validator,
                    )

            digest = hashlib.sha256()
            if append:
                self._hash_download(destination, policy_check, digest=digest)
                flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
            else:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                flags |= getattr(os, "O_NOFOLLOW", 0)

            try:
                descriptor = os.open(destination, flags, 0o600)
            except OSError as exc:
                raise OverdriveError(
                    "Could not create a private temporary download file."
                ) from exc
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or (append and info.st_size != existing):
                os.close(descriptor)
                raise OverdriveError("Resumable download file changed during transfer.")

            written = existing
            try:
                mode = "ab" if append else "wb"
                with os.fdopen(descriptor, mode) as handle:
                    if progress_callback:
                        progress_callback(written, target_total)
                    while True:
                        if policy_check:
                            policy_check()
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes or (target_total and written > target_total):
                            raise OverdriveError(
                                "Recording exceeded the configured size limit."
                            )
                        handle.write(chunk)
                        digest.update(chunk)
                        if progress_callback:
                            progress_callback(written, target_total)
                    if policy_check:
                        policy_check()
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                # A valid prefix is intentionally retained for policy pauses,
                # explicit cancellation, timeouts, and other interrupted reads.
                raise

        if target_total and written != target_total:
            raise OverdriveError(
                f"Recording transfer ended at {written} of {target_total} bytes."
            )
        return written, digest.hexdigest()

    @staticmethod
    def _partial_metadata_path(destination: Path) -> Path:
        return destination.with_name(destination.name + ".meta")

    @classmethod
    def _discard_partial(cls, destination: Path) -> None:
        for path in (destination, cls._partial_metadata_path(destination)):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    def discard_resume_metadata(cls, destination: Path) -> None:
        try:
            cls._partial_metadata_path(destination).unlink(missing_ok=True)
        except OSError:
            pass

    @classmethod
    def _load_partial_metadata(
        cls,
        destination: Path,
        *,
        source_identity: str,
        expected_size: int,
    ) -> dict[str, Any] | None:
        metadata_path = cls._partial_metadata_path(destination)
        try:
            info = metadata_path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024:
                return None
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(metadata_path, flags)
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if (
            payload.get("source_identity") != source_identity
            or payload.get("expected_size") != expected_size
            or payload.get("validator_header") not in {"etag", "last-modified"}
            or not isinstance(payload.get("validator_value"), str)
            or not payload.get("validator_value")
            or not isinstance(payload.get("total_size"), int)
            or int(payload["total_size"]) <= 0
        ):
            return None
        if expected_size and int(payload["total_size"]) != expected_size:
            return None
        return payload

    @classmethod
    def resumable_size(
        cls,
        destination: Path,
        *,
        source_identity: str,
        expected_size: int,
    ) -> int:
        metadata = cls._load_partial_metadata(
            destination,
            source_identity=source_identity,
            expected_size=max(0, int(expected_size)),
        )
        if metadata is None:
            return 0
        try:
            info = destination.lstat()
        except OSError:
            return 0
        if not stat.S_ISREG(info.st_mode):
            return 0
        size = max(0, int(info.st_size))
        return size if size <= int(metadata["total_size"]) else 0

    @staticmethod
    def _response_status(response: Any) -> int:
        status = getattr(response, "status", None)
        if status is None:
            getcode = getattr(response, "getcode", None)
            status = getcode() if callable(getcode) else None
        return int(status or 200)

    @staticmethod
    def _response_headers(response: Any) -> dict[str, str]:
        source = getattr(response, "headers", None)
        if source is None:
            return {}
        items = source.items() if hasattr(source, "items") else []
        return {str(key).lower(): str(value).strip() for key, value in items}

    @staticmethod
    def _header_int(headers: dict[str, str], key: str) -> int | None:
        value = headers.get(key)
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise OverdriveError("Vehicle returned an invalid download size.") from exc
        if parsed < 0:
            raise OverdriveError("Vehicle returned an invalid download size.")
        return parsed

    @staticmethod
    def _parse_content_range(value: str) -> tuple[int, int, int] | None:
        match = _CONTENT_RANGE_RE.fullmatch(value.strip())
        if not match:
            return None
        return tuple(int(part) for part in match.groups())  # type: ignore[return-value]

    @staticmethod
    def _select_validator(headers: dict[str, str]) -> tuple[str, str] | None:
        etag = headers.get("etag", "").strip()
        if etag and not etag.startswith("W/"):
            return "etag", etag
        modified = headers.get("last-modified", "").strip()
        return ("last-modified", modified) if modified else None

    @staticmethod
    def _validator_matches(metadata: dict[str, Any], headers: dict[str, str]) -> bool:
        key = str(metadata.get("validator_header") or "")
        return bool(key and headers.get(key) == metadata.get("validator_value"))

    @staticmethod
    def _write_partial_metadata(
        metadata_path: Path,
        *,
        source_identity: str,
        expected_size: int,
        total_size: int,
        validator: tuple[str, str],
    ) -> None:
        payload = json.dumps(
            {
                "source_identity": source_identity,
                "expected_size": expected_size,
                "total_size": total_size,
                "validator_header": validator[0],
                "validator_value": validator[1],
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        temporary = metadata_path.with_name(
            f".{metadata_path.name}.{secrets.token_hex(8)}.tmp"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, metadata_path)
        except OSError as exc:
            raise OverdriveError("Could not store resumable download metadata.") from exc
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _hash_download(
        path: Path,
        policy_check: Callable[[], None] | None,
        *,
        digest: Any | None = None,
    ) -> tuple[int, str]:
        digest = digest or hashlib.sha256()
        size = 0
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise OverdriveError("Could not read the resumable download file.") from exc
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise OverdriveError("Resumable download path is not a regular file.")
            while True:
                if policy_check:
                    policy_check()
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
        return size, digest.hexdigest()

    @staticmethod
    def encoded_filename(filename: str) -> str:
        return quote(filename, safe="")
