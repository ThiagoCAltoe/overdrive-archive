from __future__ import annotations

import hmac
import os
import tempfile
import threading
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from app.auth import (
    _SameOriginRedirectHandler,
    AuthError,
    AuthManager,
    AuthRateLimited,
    hash_password,
    normalize_otp_provider,
    validate_webhook_url,
    verify_password,
)
from app.db import Database


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(
            os.environ,
            {
                "ARCHIVE_AUTH_LOCAL_ENABLED": "true",
                "ARCHIVE_ADMIN_USERNAME": "admin",
                "ARCHIVE_ADMIN_PASSWORD": "correct-horse-battery-staple",
                "ARCHIVE_ADMIN_PASSWORD_FILE": "",
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "",
                "ARCHIVE_TELEGRAM_BOT_TOKEN_FILE": "",
                "ARCHIVE_TELEGRAM_CHAT_ID": "",
                "ARCHIVE_WHATSAPP_WEBHOOK_URL": "",
                "ARCHIVE_WHATSAPP_WEBHOOK_TOKEN": "",
                "ARCHIVE_WHATSAPP_WEBHOOK_TOKEN_FILE": "",
                "ARCHIVE_WHATSAPP_RECIPIENT": "",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.db = Database(Path(self.temp.name) / "archive.sqlite3")
        self.auth = AuthManager(self.db, b"a" * 48)

    def test_password_hash_is_salted_and_verifiable(self) -> None:
        first = hash_password("password")
        second = hash_password("password")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("password", first))
        self.assertFalse(verify_password("wrong", first))

    def test_local_login_creates_and_revokes_session(self) -> None:
        result = self.auth.authenticate_local(
            "admin",
            "correct-horse-battery-staple",
            "127.0.0.1",
        )
        self.assertEqual(result.method, "local")
        self.assertTrue(self.auth.validate_session(result.token))
        self.auth.revoke_session(result.token)
        self.assertFalse(self.auth.validate_session(result.token))

    def test_account_locks_after_repeated_failures(self) -> None:
        with patch("app.auth.time.sleep"):
            for _ in range(8):
                with self.assertRaises(AuthError):
                    self.auth.authenticate_local(
                        "admin",
                        "wrong-password",
                        "198.51.100.10",
                    )
            with self.assertRaises(AuthRateLimited):
                self.auth.authenticate_local(
                    "admin",
                    "correct-horse-battery-staple",
                    "198.51.100.11",
                )

    def test_optional_telegram_otp_is_single_use(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        sent: list[tuple[str, str]] = []
        auth._dispatch_otp = lambda provider, code: sent.append((provider, code))
        with patch("app.auth.secrets.randbelow", return_value=123456):
            auth.request_otp("telegram", "203.0.113.20")
        self.assertEqual(sent, [("telegram", "123456")])
        result = auth.verify_otp("telegram", "123456", "203.0.113.20")
        self.assertEqual(result.method, "telegram")
        with self.assertRaises(AuthError):
            auth.verify_otp("telegram", "123456", "203.0.113.20")

    def test_otp_cannot_create_two_sessions_concurrently(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
            concurrent_auth = AuthManager(self.db, b"b" * 48)
        auth._dispatch_otp = lambda provider, code: None
        with patch("app.auth.secrets.randbelow", return_value=123456):
            auth.request_otp("telegram", "203.0.113.22")

        start = threading.Barrier(3)
        compare = threading.Barrier(2)
        result_lock = threading.Lock()
        successes = []
        failures: list[AuthError] = []
        original_compare = hmac.compare_digest

        def synchronized_compare(left, right):
            try:
                compare.wait(timeout=0.5)
            except threading.BrokenBarrierError:
                pass
            return original_compare(left, right)

        def verify_code(manager):
            start.wait()
            try:
                result = manager.verify_otp(
                    "telegram",
                    "123456",
                    "203.0.113.22",
                )
            except AuthError as exc:
                with result_lock:
                    failures.append(exc)
            else:
                with result_lock:
                    successes.append(result)

        threads = [
            threading.Thread(target=verify_code, args=(manager,))
            for manager in (auth, concurrent_auth)
        ]
        with patch(
            "app.auth.hmac.compare_digest",
            side_effect=synchronized_compare,
        ):
            for thread in threads:
                thread.start()
            start.wait()
            for thread in threads:
                thread.join()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        with self.db.connect() as conn:
            session_count = conn.execute(
                """
                SELECT COUNT(*) FROM auth_sessions
                 WHERE method='telegram' AND revoked_at IS NULL
                """
            ).fetchone()[0]
            code = conn.execute(
                "SELECT used_at FROM otp_codes WHERE provider='telegram'"
            ).fetchone()
        self.assertEqual(session_count, 1)
        self.assertIsNotNone(code["used_at"])

    def test_otp_is_bound_to_the_requesting_identity(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        auth._dispatch_otp = lambda provider, code: None
        with patch("app.auth.secrets.randbelow", return_value=654321):
            auth.request_otp("telegram", "203.0.113.20")
        with self.assertRaises(AuthError):
            auth.verify_otp("telegram", "654321", "203.0.113.99")
        result = auth.verify_otp("telegram", "654321", "203.0.113.20")
        self.assertEqual(result.method, "telegram")

    def test_request_from_another_identity_does_not_invalidate_otp(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        auth._dispatch_otp = lambda provider, code: None
        with patch("app.auth.secrets.randbelow", side_effect=[111111, 222222]):
            auth.request_otp("telegram", "203.0.113.20")
            auth.request_otp("telegram", "203.0.113.21")
        result = auth.verify_otp("telegram", "111111", "203.0.113.20")
        self.assertEqual(result.method, "telegram")

    def test_otp_request_limit_is_per_identity_before_provider_ceiling(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        auth._dispatch_otp = lambda provider, code: None
        for _ in range(5):
            auth.request_otp("telegram", "203.0.113.20")
        with self.assertRaises(AuthRateLimited):
            auth.request_otp("telegram", "203.0.113.20")
        auth.request_otp("telegram", "203.0.113.21")

    def test_failed_otp_deliveries_still_consume_the_request_limit(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)

        dispatches: list[tuple[str, str]] = []

        def fail_delivery(provider, code):
            dispatches.append((provider, code))
            raise RuntimeError("provider unavailable")

        auth._dispatch_otp = fail_delivery
        for _ in range(5):
            with self.assertRaises(AuthError) as raised:
                auth.request_otp("telegram", "203.0.113.30")
            self.assertNotIsInstance(raised.exception, AuthRateLimited)
        with self.assertRaises(AuthRateLimited):
            auth.request_otp("telegram", "203.0.113.30")
        self.assertEqual(len(dispatches), 5)
        with self.db.connect() as conn:
            event_count = conn.execute(
                "SELECT COUNT(*) FROM auth_events WHERE kind='otp_request'"
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT used_at FROM otp_codes WHERE provider='telegram'"
            ).fetchall()
        self.assertEqual(event_count, 5)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["used_at"] is not None for row in rows))

    def test_failed_otp_delivery_does_not_invalidate_the_previous_code(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        auth._dispatch_otp = lambda provider, code: None
        first_time = 1_700_000_000
        with (
            patch("app.auth.time.time", return_value=first_time),
            patch("app.auth.secrets.randbelow", return_value=111111),
        ):
            auth.request_otp("telegram", "203.0.113.31")

        def fail_delivery(provider, code):
            raise RuntimeError("provider unavailable")

        auth._dispatch_otp = fail_delivery
        with (
            patch("app.auth.time.time", return_value=first_time + 1),
            patch("app.auth.secrets.randbelow", return_value=222222),
        ):
            with self.assertRaises(AuthError):
                auth.request_otp("telegram", "203.0.113.31")

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at,used_at FROM otp_codes
                 WHERE provider='telegram'
                 ORDER BY created_at
                """
            ).fetchall()
        self.assertEqual(
            [(row["created_at"], row["used_at"]) for row in rows],
            [
                (first_time, None),
                (first_time + 1, first_time + 1),
            ],
        )
        with patch("app.auth.time.time", return_value=first_time + 2):
            with self.assertRaises(AuthError):
                auth.verify_otp("telegram", "222222", "203.0.113.31")
            result = auth.verify_otp(
                "telegram",
                "111111",
                "203.0.113.31",
            )
        self.assertEqual(result.method, "telegram")

    def test_otp_request_reservation_is_atomic_under_concurrency(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auths = [
                AuthManager(self.db, b"b" * 48)
                for _ in range(4)
            ]
        auth = auths[0]
        identity = "203.0.113.32"
        fixed_time = 1_700_000_100
        with patch("app.auth.time.time", return_value=fixed_time):
            for _ in range(4):
                auth._record_event("otp_request", identity, "telegram")

        barrier = threading.Barrier(5)
        result_lock = threading.Lock()
        dispatches: list[str] = []
        successes = 0
        rate_limits: list[AuthRateLimited] = []
        unexpected: list[Exception] = []

        def dispatch(provider, code):
            with result_lock:
                dispatches.append(code)

        def request_code(manager):
            nonlocal successes
            barrier.wait()
            try:
                manager.request_otp("telegram", identity)
            except AuthRateLimited as exc:
                with result_lock:
                    rate_limits.append(exc)
            except Exception as exc:
                with result_lock:
                    unexpected.append(exc)
            else:
                with result_lock:
                    successes += 1

        for manager in auths:
            manager._dispatch_otp = dispatch
        threads = [
            threading.Thread(target=request_code, args=(manager,))
            for manager in auths
        ]
        with patch("app.auth.time.time", return_value=fixed_time):
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()

        self.assertEqual(unexpected, [])
        self.assertEqual(successes, 1)
        self.assertEqual(len(rate_limits), 3)
        self.assertTrue(
            all(exc.retry_after == 900 for exc in rate_limits)
        )
        self.assertEqual(len(dispatches), 1)
        with self.db.connect() as conn:
            event_count = conn.execute(
                "SELECT COUNT(*) FROM auth_events WHERE kind='otp_request'"
            ).fetchone()[0]
        self.assertEqual(event_count, 5)

    def test_otp_audit_failure_rolls_back_pending_code(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        identity = "203.0.113.33"
        first_time = 1_700_000_200
        auth._dispatch_otp = lambda provider, code: None
        with (
            patch("app.auth.time.time", return_value=first_time),
            patch("app.auth.secrets.randbelow", return_value=111111),
        ):
            auth.request_otp("telegram", identity)

        dispatches: list[str] = []
        auth._dispatch_otp = (
            lambda provider, code: dispatches.append(code)
        )
        with (
            patch.object(
                auth,
                "_record_event",
                side_effect=RuntimeError("audit unavailable"),
            ),
            patch("app.auth.time.time", return_value=first_time + 1),
            patch("app.auth.secrets.randbelow", return_value=222222),
        ):
            with self.assertRaises(RuntimeError):
                auth.request_otp("telegram", identity)

        self.assertEqual(dispatches, [])
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at,used_at FROM otp_codes
                 WHERE provider='telegram'
                """
            ).fetchall()
            event_count = conn.execute(
                "SELECT COUNT(*) FROM auth_events WHERE kind='otp_request'"
            ).fetchone()[0]
        self.assertEqual(
            [(row["created_at"], row["used_at"]) for row in rows],
            [(first_time, None)],
        )
        self.assertEqual(event_count, 1)
        with patch("app.auth.time.time", return_value=first_time + 2):
            result = auth.verify_otp("telegram", "111111", identity)
        self.assertEqual(result.method, "telegram")

    def test_interrupted_otp_delivery_keeps_pending_code_inactive(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        identity = "203.0.113.34"
        first_time = 1_700_000_300
        auth._dispatch_otp = lambda provider, code: None
        with (
            patch("app.auth.time.time", return_value=first_time),
            patch("app.auth.secrets.randbelow", return_value=111111),
        ):
            auth.request_otp("telegram", identity)

        def interrupt_delivery(provider, code):
            raise KeyboardInterrupt()

        auth._dispatch_otp = interrupt_delivery
        with (
            patch("app.auth.time.time", return_value=first_time + 1),
            patch("app.auth.secrets.randbelow", return_value=222222),
        ):
            with self.assertRaises(KeyboardInterrupt):
                auth.request_otp("telegram", identity)

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at,used_at FROM otp_codes
                 WHERE provider='telegram'
                 ORDER BY created_at
                """
            ).fetchall()
            event_count = conn.execute(
                "SELECT COUNT(*) FROM auth_events WHERE kind='otp_request'"
            ).fetchone()[0]
        self.assertEqual(
            [(row["created_at"], row["used_at"]) for row in rows],
            [
                (first_time, None),
                (first_time + 1, first_time + 1),
            ],
        )
        self.assertEqual(event_count, 2)
        with patch("app.auth.time.time", return_value=first_time + 2):
            result = auth.verify_otp("telegram", "111111", identity)
        self.assertEqual(result.method, "telegram")

    def test_otp_provider_has_a_separate_higher_delivery_ceiling(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        auth._dispatch_otp = lambda provider, code: None
        for index in range(30):
            auth._record_event("otp_request", f"203.0.113.{index}", "telegram")
        with self.assertRaises(AuthRateLimited):
            auth.request_otp("telegram", "198.51.100.1")

    def test_password_rotation_revokes_existing_local_sessions(self) -> None:
        result = self.auth.authenticate_local(
            "admin",
            "correct-horse-battery-staple",
            "127.0.0.1",
        )
        with patch.dict(
            os.environ,
            {"ARCHIVE_ADMIN_PASSWORD": "rotated-correct-horse-password"},
        ):
            rotated = AuthManager(self.db, b"a" * 48)
        self.assertFalse(rotated.validate_session(result.token))
        with self.assertRaises(AuthError):
            rotated.authenticate_local(
                "admin",
                "correct-horse-battery-staple",
                "127.0.0.1",
            )

    def test_username_change_disables_stale_admin_identity(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_ADMIN_USERNAME": "archive-owner",
                "ARCHIVE_ADMIN_PASSWORD": "new-owner-password-long",
            },
        ):
            changed = AuthManager(self.db, b"a" * 48)
        with self.db.connect() as conn:
            stale = conn.execute(
                "SELECT enabled FROM users WHERE username='admin'"
            ).fetchone()
        self.assertEqual(stale["enabled"], 0)
        with self.assertRaises(AuthError):
            changed.authenticate_local(
                "admin",
                "correct-horse-battery-staple",
                "127.0.0.1",
            )
        self.assertEqual(
            changed.authenticate_local(
                "archive-owner",
                "new-owner-password-long",
                "127.0.0.1",
            ).subject,
            "archive-owner",
        )

    def test_malformed_otp_is_rate_limited_before_unbounded_writes(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        with patch("app.auth.time.sleep"):
            for _ in range(8):
                with self.assertRaises(AuthError):
                    auth.verify_otp("telegram", "not-a-code", "203.0.113.21")
            with self.assertRaises(AuthRateLimited):
                auth.verify_otp("telegram", "not-a-code", "203.0.113.21")
        with self.db.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM auth_events WHERE kind='login_failure'"
            ).fetchone()[0]
        self.assertEqual(count, 8)

    def test_pending_otp_attempt_blocks_concurrent_brute_force(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
            concurrent_auth = AuthManager(self.db, b"b" * 48)
        identity = "203.0.113.23"
        rate_account = auth._otp_rate_account("telegram", identity)
        for _ in range(7):
            auth._record_event("login_failure", identity, rate_account)

        sleep_entered = threading.Event()
        release_sleep = threading.Event()
        result_lock = threading.Lock()
        sleep_calls = 0
        first_failures: list[AuthError] = []
        unexpected: list[Exception] = []

        def blocking_sleep(seconds):
            nonlocal sleep_calls
            with result_lock:
                sleep_calls += 1
                call_number = sleep_calls
            if call_number == 1:
                sleep_entered.set()
                release_sleep.wait(timeout=5)

        def first_verification():
            try:
                auth.verify_otp("telegram", "000000", identity)
            except AuthError as exc:
                with result_lock:
                    first_failures.append(exc)
            except Exception as exc:
                with result_lock:
                    unexpected.append(exc)

        thread = threading.Thread(target=first_verification)
        with patch("app.auth.time.sleep", side_effect=blocking_sleep):
            thread.start()
            try:
                self.assertTrue(sleep_entered.wait(timeout=5))
                with self.assertRaises(AuthRateLimited):
                    concurrent_auth.verify_otp(
                        "telegram",
                        "000001",
                        identity,
                    )
            finally:
                release_sleep.set()
                thread.join()

        self.assertEqual(unexpected, [])
        self.assertEqual(len(first_failures), 1)
        self.assertEqual(sleep_calls, 1)
        with self.db.connect() as conn:
            failure_count = conn.execute(
                """
                SELECT COUNT(*) FROM auth_events
                 WHERE kind='login_failure'
                """
            ).fetchone()[0]
            pending_count = conn.execute(
                """
                SELECT COUNT(*) FROM auth_events
                 WHERE kind='login_pending'
                """
            ).fetchone()[0]
        self.assertEqual(failure_count, 8)
        self.assertEqual(pending_count, 0)

    def test_one_identity_cannot_globally_lock_an_otp_provider(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_TELEGRAM_BOT_TOKEN": "test-token",
                "ARCHIVE_TELEGRAM_CHAT_ID": "1234",
            },
        ):
            auth = AuthManager(self.db, b"b" * 48)
        with patch("app.auth.time.sleep"):
            for _ in range(8):
                with self.assertRaises(AuthError):
                    auth.verify_otp("telegram", "bad", "203.0.113.20")
            with self.assertRaises(AuthRateLimited):
                auth.verify_otp("telegram", "bad", "203.0.113.20")
            try:
                auth.verify_otp("telegram", "bad", "203.0.113.21")
            except AuthRateLimited as exc:
                self.fail(f"OTP provider was locked globally: {exc}")
            except AuthError:
                pass

    def test_authentication_concurrency_is_bounded(self) -> None:
        self.auth._auth_slots = threading.BoundedSemaphore(1)
        self.auth._auth_slots.acquire()
        self.addCleanup(self.auth._auth_slots.release)
        with self.assertRaises(AuthRateLimited):
            self.auth.authenticate_local(
                "admin",
                "correct-horse-battery-staple",
                "127.0.0.1",
            )

    def test_interrupted_login_attempt_keeps_a_conservative_reservation(self) -> None:
        identity = "198.51.100.12"
        fixed_time = 1_700_000_400
        with patch("app.auth.time.time", return_value=fixed_time):
            for _ in range(7):
                self.auth._record_event(
                    "login_failure",
                    identity,
                    "admin",
                )
            with (
                patch(
                    "app.auth.verify_password",
                    side_effect=KeyboardInterrupt(),
                ),
                patch("app.auth.time.sleep"),
                self.assertRaises(KeyboardInterrupt),
            ):
                self.auth.authenticate_local(
                    "admin",
                    "correct-horse-battery-staple",
                    identity,
                )

        with self.db.connect() as conn:
            kinds = {
                row["kind"]: row["count"]
                for row in conn.execute(
                    """
                    SELECT kind,COUNT(*) AS count FROM auth_events
                     GROUP BY kind
                    """
                ).fetchall()
            }
        self.assertEqual(kinds, {"login_failure": 7, "login_pending": 1})
        with patch("app.auth.time.time", return_value=fixed_time):
            with self.assertRaises(AuthRateLimited):
                self.auth.authenticate_local(
                    "admin",
                    "correct-horse-battery-staple",
                    identity,
                )

    def test_oversized_password_is_rejected_without_scrypt(self) -> None:
        with patch("app.auth.verify_password") as verify:
            with self.assertRaises(AuthError):
                self.auth.authenticate_local(
                    "admin",
                    "x" * 1025,
                    "127.0.0.1",
                )
        verify.assert_not_called()

    def test_otp_provider_is_a_small_allowlisted_value(self) -> None:
        self.assertEqual(normalize_otp_provider(" Telegram "), "telegram")
        for value in ("email", "telegram\nforged", "x" * 100, {"id": "telegram"}):
            with self.subTest(value=value):
                with self.assertRaises(AuthError):
                    normalize_otp_provider(value)

    def test_webhook_url_requires_https_for_non_local_hosts(self) -> None:
        self.assertEqual(
            validate_webhook_url("https://gateway.example/send"),
            "https://gateway.example/send",
        )
        self.assertEqual(
            validate_webhook_url("http://whatsapp-gateway/send"),
            "http://whatsapp-gateway/send",
        )
        with self.assertRaises(AuthError):
            validate_webhook_url("http://gateway.example/send")
        with self.assertRaises(AuthError):
            validate_webhook_url("https://user:pass@gateway.example/send")

    def test_public_example_password_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_ADMIN_PASSWORD": "replace-with-a-long-random-password",
            },
        ):
            with self.assertRaises(AuthError):
                AuthManager(self.db, b"c" * 48)

    def test_local_credentials_must_fit_login_limits(self) -> None:
        with patch.dict(
            os.environ,
            {"ARCHIVE_ADMIN_USERNAME": "x" * 129},
        ):
            with self.assertRaises(AuthError):
                AuthManager(self.db, b"c" * 48)
        with patch.dict(
            os.environ,
            {"ARCHIVE_ADMIN_PASSWORD": "x" * 1025},
        ):
            with self.assertRaises(AuthError):
                AuthManager(self.db, b"c" * 48)

    def test_provider_configuration_values_have_length_limits(self) -> None:
        cases = (
            {"ARCHIVE_TELEGRAM_BOT_TOKEN": "x" * 4097},
            {"ARCHIVE_TELEGRAM_CHAT_ID": "x" * 257},
            {"ARCHIVE_WHATSAPP_WEBHOOK_TOKEN": "x" * 4097},
            {"ARCHIVE_WHATSAPP_RECIPIENT": "x" * 513},
        )
        for candidate in cases:
            with self.subTest(variable=next(iter(candidate))):
                with patch.dict(os.environ, candidate):
                    with self.assertRaises(AuthError):
                        AuthManager(self.db, b"c" * 48)

    def test_secret_file_values_are_bounded(self) -> None:
        secret = Path(self.temp.name) / "provider.secret"
        secret.write_text("x" * 4097, encoding="utf-8")
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_WHATSAPP_WEBHOOK_TOKEN": "",
                "ARCHIVE_WHATSAPP_WEBHOOK_TOKEN_FILE": str(secret),
            },
        ):
            with self.assertRaises(AuthError):
                AuthManager(self.db, b"c" * 48)

        secret.write_text("x" * 4096 + "\n", encoding="utf-8")
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_WHATSAPP_WEBHOOK_TOKEN": "",
                "ARCHIVE_WHATSAPP_WEBHOOK_TOKEN_FILE": str(secret),
            },
        ):
            auth = AuthManager(self.db, b"c" * 48)
        self.assertEqual(auth.whatsapp_webhook_token, "x" * 4096)

        with patch.dict(
            os.environ,
            {
                "ARCHIVE_WHATSAPP_WEBHOOK_TOKEN_FILE": "x" * 4097,
            },
        ):
            with self.assertRaises(AuthError):
                AuthManager(self.db, b"c" * 48)

        password = Path(self.temp.name) / "admin.secret"
        password.write_text("x" * 1025, encoding="utf-8")
        with patch.dict(
            os.environ,
            {
                "ARCHIVE_ADMIN_PASSWORD": "",
                "ARCHIVE_ADMIN_PASSWORD_FILE": str(password),
            },
        ):
            with self.assertRaises(AuthError):
                AuthManager(self.db, b"c" * 48)

    def test_webhook_redirects_cannot_change_origin_or_protocol(self) -> None:
        handler = _SameOriginRedirectHandler()
        request = Request(
            "https://gateway.example/send",
            data=b"{}",
            headers={"Authorization": "Bearer secret"},
            method="POST",
        )
        headers = Message()
        with self.assertRaises(HTTPError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                headers,
                "https://other.example/sink",
            )
        with self.assertRaises(HTTPError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                headers,
                "http://gateway.example/sink",
            )
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            headers,
            "https://gateway.example/next",
        )
        self.assertEqual(redirected.full_url, "https://gateway.example/next")
        self.assertEqual(redirected.get_header("Authorization"), "Bearer secret")


if __name__ == "__main__":
    unittest.main()
