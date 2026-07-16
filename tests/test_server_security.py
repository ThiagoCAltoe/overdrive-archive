from __future__ import annotations

import os
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.config import SettingsError
from app.server import (
    ArchiveHTTPServer,
    Handler,
    REQUEST_SOCKET_TIMEOUT,
    _apply_vehicle_token_policy,
    _prepare_runtime_directories,
    _secret,
)


class ServerSecurityTests(unittest.TestCase):
    def test_accepted_socket_receives_a_timeout(self) -> None:
        connection = Mock()
        expected = (connection, ("127.0.0.1", 12345))
        server = object.__new__(ArchiveHTTPServer)
        with patch(
            "http.server.ThreadingHTTPServer.get_request",
            return_value=expected,
        ):
            actual = server.get_request()
        self.assertEqual(actual, expected)
        connection.settimeout.assert_called_once_with(REQUEST_SOCKET_TIMEOUT)

    def test_oversized_login_is_rejected_before_authentication(self) -> None:
        handler = object.__new__(Handler)
        handler._read_json = lambda: {
            "username": "admin",
            "password": "x" * 1025,
        }
        handler._json = Mock()
        handler.server = SimpleNamespace(auth=Mock())
        Handler._handle_login(handler)
        handler.server.auth.authenticate_local.assert_not_called()
        self.assertEqual(handler._json.call_args.args[0], 401)

    def test_vehicle_origin_change_does_not_carry_saved_token(self) -> None:
        current = {
            "base_url": "https://vehicle.example",
            "device_token": "saved-secret",
        }
        changed = {
            "base_url": "https://other.example",
            "device_token": "",
            "device_id": "old-device",
            "app_version": "1.0",
        }
        _apply_vehicle_token_policy(changed, current)
        self.assertEqual(changed["device_token"], "")
        self.assertEqual(changed["device_id"], "")
        self.assertEqual(changed["app_version"], "")
        self.assertEqual(changed["locale"], "")
        self.assertEqual(changed["distance_unit"], "")

        same_origin = {
            "base_url": "https://vehicle.example:443/new-path",
            "device_token": "",
        }
        _apply_vehicle_token_policy(same_origin, current)
        self.assertEqual(same_origin["device_token"], "saved-secret")

        replacement = {
            "base_url": "https://other.example",
            "device_token": "new-secret",
        }
        _apply_vehicle_token_policy(replacement, current)
        self.assertEqual(replacement["device_token"], "new-secret")

        for changed_origin in (
            "http://vehicle.example",
            "https://vehicle.example:8443",
        ):
            changed = {
                "base_url": changed_origin,
                "device_token": "",
            }
            _apply_vehicle_token_policy(changed, current)
            self.assertEqual(changed["device_token"], "")

    def test_vehicle_token_clear_requires_a_boolean(self) -> None:
        current = {
            "base_url": "https://vehicle.example",
            "device_token": "saved-secret",
        }
        keep = {
            "base_url": "https://vehicle.example",
            "device_token": "",
            "clear_device_token": False,
        }
        _apply_vehicle_token_policy(keep, current)
        self.assertEqual(keep["device_token"], "saved-secret")

        clear = {
            "base_url": "https://vehicle.example",
            "device_token": "",
            "clear_device_token": True,
        }
        _apply_vehicle_token_policy(clear, current)
        self.assertEqual(clear["device_token"], "")

        with self.assertRaises(SettingsError):
            _apply_vehicle_token_policy(
                {
                    "base_url": "https://vehicle.example",
                    "device_token": "",
                    "clear_device_token": "false",
                },
                current,
            )

    def test_existing_archive_permissions_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            archive_root = root / "archive"
            data_dir.mkdir()
            archive_root.mkdir()
            data_dir.chmod(0o775)
            archive_root.chmod(0o770)

            _prepare_runtime_directories(data_dir, archive_root)

            self.assertEqual(data_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(archive_root.stat().st_mode & 0o777, 0o770)

    def test_empty_default_archive_root_is_secured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            archive_root = root / "archive"
            archive_root.mkdir()
            archive_root.chmod(0o755)

            _prepare_runtime_directories(data_dir, archive_root)

            self.assertEqual(archive_root.stat().st_mode & 0o777, 0o700)

    def test_nonempty_default_archive_root_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            archive_root = root / "archive"
            archive_root.mkdir()
            (archive_root / "operator-managed").mkdir()
            archive_root.chmod(0o755)

            _prepare_runtime_directories(data_dir, archive_root)

            self.assertEqual(archive_root.stat().st_mode & 0o777, 0o755)

    def test_new_runtime_directories_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            archive_root = root / "archive"

            _prepare_runtime_directories(data_dir, archive_root)

            self.assertEqual(data_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(archive_root.stat().st_mode & 0o777, 0o700)

    def test_session_secret_uses_exclusive_random_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictable = root / "session.part"
            predictable.symlink_to(root / "outside")
            secret = _secret(root)
            self.assertEqual(len(secret), 48)
            self.assertTrue(predictable.is_symlink())
            self.assertEqual((root / "session.key").stat().st_mode & 0o777, 0o600)

    def test_session_secret_refuses_a_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.write_bytes(b"x" * 48)
            (root / "session.key").symlink_to(outside)
            with self.assertRaises(RuntimeError):
                _secret(root)

    def test_existing_session_secret_permissions_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "session.key"
            path.write_bytes(b"x" * 48)
            path.chmod(0o644)
            self.assertEqual(_secret(root), b"x" * 48)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_session_secret_rejects_a_fifo_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.mkfifo(root / "session.key")
            with self.assertRaises(RuntimeError):
                _secret(root)


if __name__ == "__main__":
    unittest.main()
