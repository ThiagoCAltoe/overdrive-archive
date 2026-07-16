from __future__ import annotations

import os
import sys
from pathlib import Path


def _numeric_id(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a numeric user or group ID.") from exc
    if value < 1 or value > 2_147_483_647:
        raise ValueError(f"{name} must be between 1 and 2147483647.")
    return value


def _can_write_as(path: Path, uid: int, gid: int) -> bool:
    pid = os.fork()
    if pid == 0:
        probe = path / f".overdrive-archive-write-test-{os.getpid()}"
        try:
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)
            descriptor = os.open(
                probe,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                os.write(descriptor, b"ok")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            probe.unlink()
        except BaseException:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
            os._exit(1)
        os._exit(0)
    _, status = os.waitpid(pid, 0)
    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


def prepare_path(path: Path, uid: int, gid: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if _can_write_as(path, uid, gid):
        print(f"{path}: writable by {uid}:{gid}")
        return

    try:
        os.chown(path, uid, gid)
    except OSError as exc:
        raise PermissionError(
            f"{path} is not writable by {uid}:{gid}, and its ownership could "
            f"not be adjusted: {exc}. Configure ARCHIVE_UID/ARCHIVE_GID to "
            "match the host or NAS permissions."
        ) from exc

    if not _can_write_as(path, uid, gid):
        raise PermissionError(
            f"{path} is still not writable by {uid}:{gid} after ownership setup."
        )
    print(f"{path}: ownership prepared for {uid}:{gid}")


def main() -> int:
    os.umask(0o077)
    try:
        uid = _numeric_id("ARCHIVE_UID", 10001)
        gid = _numeric_id("ARCHIVE_GID", 10001)
        for raw_path in (
            os.environ.get("ARCHIVE_DATA_DIR", "/data"),
            os.environ.get("ARCHIVE_ROOT", "/archive"),
        ):
            prepare_path(Path(raw_path), uid, gid)
    except (OSError, ValueError) as exc:
        print(f"Storage initialization failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
