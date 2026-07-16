from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .db import Database


SESSION_TTL = 12 * 60 * 60
SESSION_IDLE = 60 * 60
OTP_TTL = 10 * 60
AUTH_MAX_CONCURRENCY = 4
PASSWORD_N = 2**15
PASSWORD_R = 8
PASSWORD_P = 1
PASSWORD_MAXMEM = 64 * 1024 * 1024
PASSWORD_INPUT_MAX = 1024
SECRET_FILE_PATH_MAX = 4096
SECRET_FILE_FORMAT_OVERHEAD = 2
OTP_PROVIDERS = frozenset({"telegram", "whatsapp"})
REJECTED_PASSWORDS = frozenset(
    {
        "replace-with-a-long-random-password",
        "replace-me-with-a-long-random-password",
        "your-secure-password-here",
    }
)


class AuthError(RuntimeError):
    pass


class AuthRateLimited(AuthError):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class AuthResult:
    token: str
    method: str
    subject: str


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved = urljoin(req.full_url, newurl)
        old = _url_origin(req.full_url)
        new = _url_origin(resolved)
        if old != new:
            raise HTTPError(
                req.full_url,
                code,
                "Cross-origin or protocol-changing redirect blocked",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, resolved)


def _b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_N,
        r=PASSWORD_R,
        p=PASSWORD_P,
        maxmem=PASSWORD_MAXMEM,
        dklen=32,
    )
    return f"scrypt${PASSWORD_N}${PASSWORD_R}${PASSWORD_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=PASSWORD_MAXMEM,
            dklen=len(_unb64(expected)),
        )
        return hmac.compare_digest(digest, _unb64(expected))
    except (ValueError, TypeError):
        return False


def normalize_otp_provider(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 16:
        raise AuthError("Invalid sign-in method.")
    provider = value.strip().lower()
    if provider not in OTP_PROVIDERS:
        raise AuthError("Invalid sign-in method.")
    return provider


def _url_origin(value: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise AuthError("Provider URL contains an invalid port.") from exc
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").casefold()
    if scheme not in {"http", "https"} or not hostname:
        raise AuthError("Provider URL must use HTTP or HTTPS.")
    return scheme, hostname, port or (443 if scheme == "https" else 80)


def _local_http_host(hostname: str) -> bool:
    host = hostname.rstrip(".").casefold()
    if (
        host == "localhost"
        or host.endswith(".localhost")
        or host.endswith(".local")
        or host == "host.docker.internal"
        or "." not in host
    ):
        return True
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local)


def validate_webhook_url(value: Any) -> str:
    if not isinstance(value, str):
        raise AuthError("WhatsApp webhook URL must be text.")
    raw = value.strip()
    if not raw:
        return ""
    if len(raw) > 2048 or "\\" in raw or any(ord(char) < 32 for char in raw):
        raise AuthError("WhatsApp webhook URL is invalid.")
    try:
        parsed = urlsplit(raw)
        _url_origin(raw)
    except ValueError as exc:
        raise AuthError("WhatsApp webhook URL is invalid.") from exc
    if parsed.username or parsed.password:
        raise AuthError("WhatsApp webhook URL must not contain credentials.")
    if parsed.fragment:
        raise AuthError("WhatsApp webhook URL must not contain a fragment.")
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme.lower() == "http" and not _local_http_host(hostname):
        raise AuthError(
            "WhatsApp webhook URL must use HTTPS unless it targets a local host."
        )
    return raw


class AuthManager:
    def __init__(self, db: Database, pepper: bytes):
        self.db = db
        self.pepper = pepper
        self._auth_slots = threading.BoundedSemaphore(AUTH_MAX_CONCURRENCY)
        self.local_enabled = os.environ.get(
            "ARCHIVE_AUTH_LOCAL_ENABLED", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.admin_username = (
            os.environ.get("ARCHIVE_ADMIN_USERNAME", "admin").strip() or "admin"
        )
        self.admin_password = _secret_env(
            "ARCHIVE_ADMIN_PASSWORD",
            PASSWORD_INPUT_MAX,
        )
        if len(self.admin_username) > 128 or any(
            ord(char) < 32 for char in self.admin_username
        ):
            raise AuthError(
                "ARCHIVE_ADMIN_USERNAME must be at most 128 printable characters."
            )

        self.telegram_bot_token = _secret_env(
            "ARCHIVE_TELEGRAM_BOT_TOKEN",
            4096,
        )
        self.telegram_chat_id = os.environ.get(
            "ARCHIVE_TELEGRAM_CHAT_ID", ""
        ).strip()
        self.whatsapp_webhook_url = validate_webhook_url(
            os.environ.get("ARCHIVE_WHATSAPP_WEBHOOK_URL", "")
        )
        self.whatsapp_webhook_token = _secret_env(
            "ARCHIVE_WHATSAPP_WEBHOOK_TOKEN",
            4096,
        )
        self.whatsapp_recipient = os.environ.get(
            "ARCHIVE_WHATSAPP_RECIPIENT", ""
        ).strip()
        if len(self.telegram_chat_id) > 256:
            raise AuthError("ARCHIVE_TELEGRAM_CHAT_ID is too long.")
        if len(self.whatsapp_recipient) > 512:
            raise AuthError("ARCHIVE_WHATSAPP_RECIPIENT is too long.")

        if self.local_enabled:
            if len(self.admin_password) < 12:
                raise AuthError(
                    "ARCHIVE_ADMIN_PASSWORD must contain at least 12 characters "
                    "when local authentication is enabled."
                )
            if len(self.admin_password) > PASSWORD_INPUT_MAX:
                raise AuthError(
                    f"ARCHIVE_ADMIN_PASSWORD must be at most "
                    f"{PASSWORD_INPUT_MAX} characters."
                )
            if self.admin_password.casefold() in REJECTED_PASSWORDS:
                raise AuthError(
                    "ARCHIVE_ADMIN_PASSWORD must not use a public example value."
                )
            self._ensure_admin()
        else:
            self._disable_local_auth()
        if not self.options()["methods"]:
            raise AuthError("At least one authentication method must be configured.")

    def _digest(self, kind: str, value: str) -> str:
        return hmac.new(
            self.pepper,
            f"{kind}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def options(self) -> dict[str, Any]:
        methods: list[dict[str, str]] = []
        if self.local_enabled:
            methods.append(
                {
                    "id": "local",
                    "label": "Username & password",
                    "description": "Local administrator account",
                }
            )
        if self.telegram_bot_token and self.telegram_chat_id:
            methods.append(
                {
                    "id": "telegram",
                    "label": "Telegram code",
                    "description": "One-time code sent to the configured Telegram chat",
                }
            )
        if self.whatsapp_webhook_url and self.whatsapp_recipient:
            methods.append(
                {
                    "id": "whatsapp",
                    "label": "WhatsApp code",
                    "description": "One-time code sent through the configured WhatsApp gateway",
                }
            )
        return {"methods": methods}

    def _ensure_admin(self) -> None:
        now = int(time.time())
        with self.db.connect() as conn:
            stale_changed = (
                conn.execute(
                    """
                    UPDATE users SET enabled=0,updated_at=?
                     WHERE username<>? AND enabled<>0
                    """,
                    (now, self.admin_username),
                ).rowcount
                > 0
            )
            row = conn.execute(
                "SELECT password_hash,enabled FROM users WHERE username=?",
                (self.admin_username,),
            ).fetchone()
            credentials_changed = stale_changed
            if row is None:
                conn.execute(
                    """
                    INSERT INTO users(username,password_hash,enabled,created_at,updated_at)
                    VALUES(?,?,1,?,?)
                    """,
                    (
                        self.admin_username,
                        hash_password(self.admin_password),
                        now,
                        now,
                    ),
                )
                credentials_changed = True
            elif (
                not row["enabled"]
                or not verify_password(self.admin_password, row["password_hash"])
            ):
                conn.execute(
                    """
                    UPDATE users SET password_hash=?,enabled=1,updated_at=?
                    WHERE username=?
                    """,
                    (hash_password(self.admin_password), now, self.admin_username),
                )
                credentials_changed = True
            if credentials_changed:
                conn.execute(
                    """
                    UPDATE auth_sessions SET revoked_at=?
                     WHERE method='local' AND revoked_at IS NULL
                    """,
                    (now,),
                )

    def _disable_local_auth(self) -> None:
        now = int(time.time())
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE users SET enabled=0,updated_at=? WHERE enabled<>0",
                (now,),
            )
            conn.execute(
                """
                UPDATE auth_sessions SET revoked_at=?
                 WHERE method='local' AND revoked_at IS NULL
                """,
                (now,),
            )

    @contextmanager
    def _auth_operation(self):
        if not self._auth_slots.acquire(blocking=False):
            raise AuthRateLimited(
                "Authentication is temporarily busy. Try again shortly.",
                2,
            )
        try:
            yield
        finally:
            self._auth_slots.release()

    def _cleanup(self, conn, now: int) -> None:
        conn.execute(
            "DELETE FROM auth_events WHERE created_at<?",
            (now - 7 * 86400,),
        )
        conn.execute(
            "DELETE FROM auth_sessions WHERE expires_at<? OR (revoked_at IS NOT NULL AND revoked_at<?)",
            (now - 86400, now - 86400),
        )
        conn.execute(
            "DELETE FROM otp_codes WHERE expires_at<? OR (used_at IS NOT NULL AND used_at<?)",
            (now - 86400, now - 86400),
        )

    @staticmethod
    def _rate_counts(
        conn,
        now: int,
        identity_hash: str,
        account_hash: str,
    ) -> tuple[int, int]:
        account_failures = conn.execute(
            """
            SELECT COUNT(*) FROM auth_events
             WHERE kind IN ('login_failure','login_pending')
               AND account_hash=? AND created_at>=?
            """,
            (account_hash, now - 1800),
        ).fetchone()[0]
        ip_failures = conn.execute(
            """
            SELECT COUNT(*) FROM auth_events
             WHERE kind IN ('login_failure','login_pending')
               AND identity_hash=? AND created_at>=?
            """,
            (identity_hash, now - 3600),
        ).fetchone()[0]
        return int(account_failures), int(ip_failures)

    @staticmethod
    def _raise_if_login_locked(
        account_failures: int,
        ip_failures: int,
    ) -> None:
        if account_failures >= 8:
            raise AuthRateLimited(
                "This account is temporarily locked after repeated failures.",
                1800,
            )
        if ip_failures >= 20:
            raise AuthRateLimited(
                "Too many failed sign-in attempts from this network.",
                3600,
            )

    def _record_event(
        self,
        kind: str,
        identity: str,
        account: str,
        *,
        conn=None,
        created_at: int | None = None,
    ) -> int:
        values = (
            kind,
            self._digest("identity", identity),
            self._digest("account", account.casefold()),
            int(time.time()) if created_at is None else created_at,
        )
        statement = """
            INSERT INTO auth_events(kind,identity_hash,account_hash,created_at)
            VALUES(?,?,?,?)
        """
        if conn is not None:
            cursor = conn.execute(statement, values)
            return int(cursor.lastrowid)
        with self.db.connect() as event_conn:
            cursor = event_conn.execute(statement, values)
            return int(cursor.lastrowid)

    def _reserve_login_attempt(
        self,
        identity: str,
        account: str,
    ) -> tuple[int, int]:
        now = int(time.time())
        identity_hash = self._digest("identity", identity)
        account_hash = self._digest("account", account.casefold())
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._cleanup(conn, now)
            account_failures, ip_failures = self._rate_counts(
                conn,
                now,
                identity_hash,
                account_hash,
            )
            self._raise_if_login_locked(account_failures, ip_failures)
            event_id = self._record_event(
                "login_pending",
                identity,
                account,
                conn=conn,
                created_at=now,
            )
        delay = (
            0
            if account_failures < 3
            else min(4, 2 ** (account_failures - 3))
        )
        return event_id, delay

    def _finish_login_attempt_failure(self, event_id: int) -> None:
        with self.db.connect() as conn:
            updated = conn.execute(
                """
                UPDATE auth_events SET kind='login_failure'
                 WHERE id=? AND kind='login_pending'
                """,
                (event_id,),
            ).rowcount
            if updated != 1:
                raise AuthError(
                    "Authentication attempt state could not be recorded."
                )

    def _finish_login_attempt_success(
        self,
        event_id: int,
        identity: str,
        account: str,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            removed = conn.execute(
                """
                DELETE FROM auth_events
                 WHERE id=? AND kind='login_pending'
                """,
                (event_id,),
            ).rowcount
            if removed != 1:
                raise AuthError(
                    "Authentication attempt state could not be cleared."
                )
            conn.execute(
                """
                DELETE FROM auth_events
                 WHERE kind='login_failure'
                   AND (identity_hash=? OR account_hash=?)
                """,
                (
                    self._digest("identity", identity),
                    self._digest("account", account.casefold()),
                ),
            )

    def authenticate_local(
        self, username: str, password: str, identity: str
    ) -> AuthResult:
        if not self.local_enabled:
            raise AuthError("Local authentication is disabled.")
        username = username.strip() if isinstance(username, str) else ""
        password = password if isinstance(password, str) else ""
        account = username if 0 < len(username) <= 128 else "unknown"
        with self._auth_operation():
            attempt_id, delay = self._reserve_login_attempt(
                identity,
                account,
            )
            if delay:
                time.sleep(delay)
            with self.db.connect() as conn:
                row = (
                    conn.execute(
                        """
                        SELECT username,password_hash,enabled FROM users
                         WHERE username=?
                        """,
                        (username,),
                    ).fetchone()
                    if account != "unknown"
                    else None
                )
            valid = bool(
                len(password) <= PASSWORD_INPUT_MAX
                and row
                and row["enabled"]
                and verify_password(password, row["password_hash"])
            )
            if not valid:
                self._finish_login_attempt_failure(attempt_id)
                raise AuthError("Invalid username or password.")
            self._finish_login_attempt_success(
                attempt_id,
                identity,
                username,
            )
            return self._create_session(username, "local")

    def _reserve_otp_request(
        self,
        provider: str,
        identity: str,
        code_id: str,
        code_hash: str,
        now: int,
    ) -> str:
        identity_hash = self._digest("identity", identity)
        account_hash = self._digest("account", provider)
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._cleanup(conn, now)
            identity_count = conn.execute(
                """
                SELECT COUNT(*) FROM auth_events
                 WHERE kind='otp_request' AND identity_hash=? AND created_at>=?
                """,
                (identity_hash, now - 900),
            ).fetchone()[0]
            provider_count = conn.execute(
                """
                SELECT COUNT(*) FROM auth_events
                 WHERE kind='otp_request' AND account_hash=? AND created_at>=?
                """,
                (account_hash, now - 900),
            ).fetchone()[0]
            if int(identity_count) >= 5:
                raise AuthRateLimited(
                    "Too many one-time code requests. Try again later.",
                    900,
                )
            if int(provider_count) >= 30:
                raise AuthRateLimited(
                    "The one-time code provider is temporarily busy.",
                    900,
                )
            self._record_event(
                "otp_request",
                identity,
                provider,
                conn=conn,
                created_at=now,
            )
            conn.execute(
                """
                INSERT INTO otp_codes(
                    id,provider,code_hash,identity_hash,created_at,expires_at,
                    used_at,attempts
                ) VALUES(?,?,?,?,?,?,?,0)
                """,
                (
                    code_id,
                    provider,
                    code_hash,
                    identity_hash,
                    now,
                    now + OTP_TTL,
                    now,
                ),
            )
        return identity_hash

    def _activate_delivered_otp(
        self,
        provider: str,
        identity_hash: str,
        code_id: str,
    ) -> None:
        now = int(time.time())
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE otp_codes SET used_at=?
                 WHERE provider=? AND identity_hash=? AND id<>?
                   AND used_at IS NULL
                """,
                (now, provider, identity_hash, code_id),
            )
            activated = conn.execute(
                """
                UPDATE otp_codes SET used_at=NULL
                 WHERE id=? AND provider=? AND identity_hash=?
                   AND used_at IS NOT NULL
                """,
                (code_id, provider, identity_hash),
            ).rowcount
            if activated != 1:
                raise AuthError(
                    "The delivered one-time code could not be activated."
                )

    def _otp_rate_account(self, provider: str, identity: str) -> str:
        identity_key = self._digest("otp-rate-identity", identity)
        return f"{provider}:{identity_key}"

    def request_otp(self, provider: str, identity: str) -> None:
        provider = normalize_otp_provider(provider)
        available = {method["id"] for method in self.options()["methods"]}
        if provider not in available:
            raise AuthError("This sign-in method is not configured.")
        with self._auth_operation():
            code = f"{secrets.randbelow(1_000_000):06d}"
            now = int(time.time())
            code_id = secrets.token_urlsafe(18)
            code_hash = self._digest("otp", f"{provider}:{code_id}:{code}")
            identity_hash = self._reserve_otp_request(
                provider,
                identity,
                code_id,
                code_hash,
                now,
            )
            try:
                self._dispatch_otp(provider, code)
            except Exception as exc:
                raise AuthError(
                    "The one-time code could not be delivered. Check the provider configuration."
                ) from exc
            self._activate_delivered_otp(provider, identity_hash, code_id)

    def verify_otp(self, provider: str, code: str, identity: str) -> AuthResult:
        provider = normalize_otp_provider(provider)
        code = code if isinstance(code, str) and len(code) <= 16 else ""
        rate_account = self._otp_rate_account(provider, identity)
        with self._auth_operation():
            attempt_id, delay = self._reserve_login_attempt(
                identity,
                rate_account,
            )
            if delay:
                time.sleep(delay)
            if not re_fullmatch_digits(code):
                self._finish_login_attempt_failure(attempt_id)
                raise AuthError("Invalid or expired one-time code.")
            now = int(time.time())
            identity_hash = self._digest("identity", identity)
            with self.db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT * FROM otp_codes
                     WHERE provider=? AND identity_hash=?
                       AND used_at IS NULL AND expires_at>=?
                     ORDER BY created_at DESC LIMIT 1
                    """,
                    (provider, identity_hash, now),
                ).fetchone()
                valid = bool(
                    row
                    and row["attempts"] < 8
                    and hmac.compare_digest(
                        row["code_hash"],
                        self._digest("otp", f"{provider}:{row['id']}:{code}"),
                    )
                )
                if row:
                    if valid:
                        consumed = conn.execute(
                            """
                            UPDATE otp_codes SET used_at=?
                             WHERE id=? AND used_at IS NULL AND expires_at>=?
                            """,
                            (now, row["id"], now),
                        ).rowcount
                        valid = consumed == 1
                    else:
                        conn.execute(
                            """
                            UPDATE otp_codes SET attempts=attempts+1
                             WHERE id=? AND used_at IS NULL
                            """,
                            (row["id"],),
                        )
            if not valid:
                self._finish_login_attempt_failure(attempt_id)
                raise AuthError("Invalid or expired one-time code.")
            self._finish_login_attempt_success(
                attempt_id,
                identity,
                rate_account,
            )
            return self._create_session("admin", provider)

    def _dispatch_otp(self, provider: str, code: str) -> None:
        message = (
            f"Your Overdrive Archive sign-in code is {code}. "
            "It expires in 10 minutes. Do not share this code."
        )
        if provider == "telegram":
            url = (
                "https://api.telegram.org/bot"
                + self.telegram_bot_token
                + "/sendMessage"
            )
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "disable_web_page_preview": True,
            }
            self._post_json(url, payload, "")
            return
        payload = {
            "recipient": self.whatsapp_recipient,
            "message": message,
            "purpose": "overdrive-archive-login",
        }
        self._post_json(
            self.whatsapp_webhook_url,
            payload,
            self.whatsapp_webhook_token,
        )

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any], bearer: str) -> None:
        validate_webhook_url(url)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Overdrive-Archive/0.1",
        }
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        request = Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers=headers,
            method="POST",
        )
        try:
            opener = build_opener(_SameOriginRedirectHandler())
            with opener.open(request, timeout=12) as response:
                if response.status < 200 or response.status >= 300:
                    raise AuthError("Provider rejected the one-time code.")
                response.read(4096)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise AuthError("Provider delivery failed.") from exc

    def _create_session(self, subject: str, method: str) -> AuthResult:
        token = secrets.token_urlsafe(48)
        now = int(time.time())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_sessions(
                    token_hash,subject,method,created_at,last_seen_at,expires_at,revoked_at
                ) VALUES(?,?,?,?,?,?,NULL)
                """,
                (
                    self._digest("session", token),
                    subject,
                    method,
                    now,
                    now,
                    now + SESSION_TTL,
                ),
            )
        return AuthResult(token=token, method=method, subject=subject)

    def validate_session(self, token: str) -> bool:
        if not token or len(token) > 300:
            return False
        now = int(time.time())
        token_hash = self._digest("session", token)
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT last_seen_at FROM auth_sessions
                 WHERE token_hash=? AND revoked_at IS NULL
                   AND expires_at>=? AND last_seen_at>=?
                """,
                (token_hash, now, now - SESSION_IDLE),
            ).fetchone()
            if row and now - int(row["last_seen_at"]) >= 60:
                conn.execute(
                    "UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?",
                    (now, token_hash),
                )
        return row is not None

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE token_hash=?",
                (int(time.time()), self._digest("session", token)),
            )


def re_fullmatch_digits(value: str) -> bool:
    return len(value) == 6 and value.isascii() and value.isdigit()


def _secret_env(name: str, maximum: int) -> str:
    raw_file_name = os.environ.get(f"{name}_FILE", "")
    if len(raw_file_name) > SECRET_FILE_PATH_MAX:
        raise AuthError(f"{name}_FILE path is too long.")
    file_name = raw_file_name.strip()
    if file_name:
        try:
            with open(file_name, "r", encoding="utf-8") as handle:
                value = handle.read(
                    maximum + SECRET_FILE_FORMAT_OVERHEAD + 1
                )
            if len(value) > maximum + SECRET_FILE_FORMAT_OVERHEAD:
                raise AuthError(f"{name}_FILE is too large.")
        except (OSError, UnicodeError) as exc:
            raise AuthError(f"Could not read {name}_FILE.") from exc
    else:
        value = os.environ.get(name, "")
    value = value.strip()
    if len(value) > maximum:
        raise AuthError(f"{name} is too long.")
    return value
