from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
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
        page = 1
        while page <= 1000:
            params: dict[str, Any] = {
                "page": page,
                "pageSize": 200,
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
            for item in recordings:
                if isinstance(item, dict):
                    yield item
            total_pages = max(1, int(payload.get("totalPages") or 1))
            if page >= total_pages or len(recordings) < 200:
                break
            page += 1

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
    ) -> tuple[int, str]:
        digest = hashlib.sha256()
        written = 0
        since_check = 0
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(destination, flags, 0o600)
        except OSError as exc:
            raise OverdriveError(
                "Could not create a private temporary download file."
            ) from exc
        with os.fdopen(descriptor, "wb") as handle, self._open(path) as response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                since_check += len(chunk)
                if written > max_bytes:
                    raise OverdriveError("Recording exceeded the configured size limit.")
                handle.write(chunk)
                digest.update(chunk)
                if policy_check and since_check >= 8 * 1024 * 1024:
                    policy_check()
                    since_check = 0
            handle.flush()
            os.fsync(handle.fileno())
        return written, digest.hexdigest()

    @staticmethod
    def encoded_filename(filename: str) -> str:
        return quote(filename, safe="")
