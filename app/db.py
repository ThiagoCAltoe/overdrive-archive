from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import default_settings, validate_settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        parent_was_missing = not self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if parent_was_missing:
            try:
                os.chmod(self.path.parent, 0o700)
            except OSError:
                pass
        self._initialize()
        self._harden_permissions()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        self._harden_permissions()
        return conn

    def _harden_permissions(self) -> None:
        for path in (
            self.path,
            Path(f"{self.path}-wal"),
            Path(f"{self.path}-shm"),
        ):
            if not path.exists():
                continue
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;

                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    items_added INTEGER NOT NULL DEFAULT 0,
                    items_skipped INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    bytes_added INTEGER NOT NULL DEFAULT 0,
                    network_type TEXT,
                    message TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_sync_runs_started
                    ON sync_runs(started_at DESC);

                CREATE TABLE IF NOT EXISTS archive_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_key TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    subtype TEXT NOT NULL DEFAULT '',
                    vehicle TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    source_timestamp INTEGER,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_archive_items_created
                    ON archive_items(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_archive_items_category
                    ON archive_items(category, created_at DESC);

                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    method TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry
                    ON auth_sessions(expires_at, revoked_at);

                CREATE TABLE IF NOT EXISTS auth_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    identity_hash TEXT NOT NULL,
                    account_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_auth_events_lookup
                    ON auth_events(kind, identity_hash, account_hash, created_at);

                CREATE TABLE IF NOT EXISTS otp_codes (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    identity_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    used_at INTEGER,
                    attempts INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_otp_active
                    ON otp_codes(provider, expires_at, used_at);
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(archive_items)").fetchall()
            }
            if "subtype" not in columns:
                conn.execute(
                    "ALTER TABLE archive_items ADD COLUMN subtype TEXT NOT NULL DEFAULT ''"
                )
            conn.executescript(
                """
                UPDATE archive_items
                   SET subtype = CASE
                       WHEN filename LIKE 'replay\\_%' ESCAPE '\\' THEN 'replay'
                       WHEN filename LIKE 'dvr\\_%' ESCAPE '\\' THEN 'oem_dashcam'
                       WHEN filename LIKE 'event\\_%' ESCAPE '\\' THEN 'surveillance'
                       WHEN filename LIKE 'proximity\\_%' ESCAPE '\\' THEN 'proximity'
                       ELSE 'drive'
                   END
                 WHERE category='recordings' AND subtype='';
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_archive_items_subtype
                    ON archive_items(category, subtype, created_at DESC)
                """
            )
            row = conn.execute("SELECT 1 FROM settings WHERE id=1").fetchone()
            if row is None:
                payload = json.dumps(default_settings(), separators=(",", ":"))
                conn.execute(
                    "INSERT INTO settings(id,payload,updated_at) VALUES(1,?,?)",
                    (payload, utc_now()),
                )
        self._harden_permissions()

    def get_settings(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM settings WHERE id=1").fetchone()
        if row is None:
            return default_settings()
        try:
            return validate_settings(json.loads(row["payload"]))
        except (json.JSONDecodeError, ValueError, TypeError):
            return default_settings()

    def save_settings(self, candidate: dict[str, Any]) -> dict[str, Any]:
        current = self.get_settings()
        normalized = validate_settings(candidate, current)
        payload = json.dumps(normalized, separators=(",", ":"), sort_keys=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings(id,payload,updated_at) VALUES(1,?,?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (payload, utc_now()),
            )
        return normalized

    def start_run(self, reason: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs(reason,status,started_at,message)
                VALUES(?, 'running', ?, '')
                """,
                (reason, utc_now()),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Could not create synchronization run.")
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        items_added: int,
        items_skipped: int,
        error_count: int,
        bytes_added: int,
        network_type: str,
        message: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                   SET status=?, finished_at=?, items_added=?, items_skipped=?,
                       error_count=?, bytes_added=?, network_type=?, message=?
                 WHERE id=?
                """,
                (
                    status,
                    utc_now(),
                    items_added,
                    items_skipped,
                    error_count,
                    bytes_added,
                    network_type[:30],
                    message[:1000],
                    run_id,
                ),
            )

    def last_scheduled_at(self) -> datetime | None:
        row = self.last_scheduled_run()
        if row is None:
            return None
        try:
            return datetime.fromisoformat(row["started_at"])
        except (TypeError, ValueError):
            return None

    def last_scheduled_run(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id,status,started_at,finished_at,message FROM sync_runs
                 WHERE reason='schedule'
                 ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def list_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def has_item(self, source_key: str) -> bool:
        return self.get_item_by_source_key(source_key) is not None

    def get_item_by_source_key(self, source_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM archive_items WHERE source_key=?", (source_key,)
            ).fetchone()
        return dict(row) if row else None

    def add_item(
        self,
        *,
        source_key: str,
        category: str,
        subtype: str,
        vehicle: str,
        filename: str,
        relative_path: str,
        media_type: str,
        size_bytes: int,
        sha256: str,
        source_timestamp: int | None,
        metadata: dict[str, Any] | list[Any],
    ) -> bool:
        payload = json.dumps(metadata, separators=(",", ":"), sort_keys=True)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO archive_items(
                    source_key,category,subtype,vehicle,filename,relative_path,media_type,
                    size_bytes,sha256,source_timestamp,metadata_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    source_key,
                    category,
                    subtype[:40],
                    vehicle,
                    filename,
                    relative_path,
                    media_type,
                    max(0, int(size_bytes)),
                    sha256,
                    source_timestamp,
                    payload,
                    utc_now(),
                ),
            )
            return cursor.rowcount == 1

    def update_item(
        self,
        *,
        source_key: str,
        category: str,
        subtype: str,
        vehicle: str,
        filename: str,
        relative_path: str,
        media_type: str,
        size_bytes: int,
        sha256: str,
        source_timestamp: int | None,
        metadata: dict[str, Any] | list[Any],
    ) -> bool:
        payload = json.dumps(metadata, separators=(",", ":"), sort_keys=True)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE archive_items
                   SET category=?,subtype=?,vehicle=?,filename=?,relative_path=?,
                       media_type=?,size_bytes=?,sha256=?,source_timestamp=?,
                       metadata_json=?
                 WHERE source_key=?
                """,
                (
                    category,
                    subtype[:40],
                    vehicle,
                    filename,
                    relative_path,
                    media_type,
                    max(0, int(size_bytes)),
                    sha256,
                    source_timestamp,
                    payload,
                    source_key,
                ),
            )
            return cursor.rowcount == 1

    def get_item(self, item_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM archive_items WHERE id=?", (item_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_items(
        self,
        *,
        limit: int = 100,
        category: str = "",
        subtype: str = "",
        search: str = "",
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 250))
        clauses: list[str] = []
        args: list[Any] = []
        if category:
            clauses.append("category=?")
            args.append(category)
        if subtype:
            clauses.append("subtype=?")
            args.append(subtype)
        if search:
            clauses.append("(filename LIKE ? ESCAPE '\\' OR vehicle LIKE ? ESCAPE '\\')")
            escaped = (
                search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            args.extend((f"%{escaped}%", f"%{escaped}%"))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        args.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id,category,subtype,vehicle,filename,relative_path,media_type,
                       size_bytes,sha256,source_timestamp,metadata_json,created_at
                  FROM archive_items
                  {where}
                 ORDER BY CASE
                     WHEN source_timestamp IS NULL OR source_timestamp<=0
                         THEN CAST(strftime('%s', created_at) AS INTEGER) * 1000
                     WHEN source_timestamp<10000000000
                         THEN source_timestamp * 1000
                     ELSE source_timestamp
                 END DESC, id DESC
                 LIMIT ?
                """,
                args,
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            totals = conn.execute(
                """
                SELECT COUNT(*) AS item_count,
                       COALESCE(SUM(size_bytes), 0) AS total_bytes
                  FROM archive_items
                """
            ).fetchone()
            categories = conn.execute(
                """
                SELECT category, COUNT(*) AS count,
                       COALESCE(SUM(size_bytes), 0) AS bytes
                  FROM archive_items
                 GROUP BY category ORDER BY category
                """
            ).fetchall()
        return {
            "item_count": int(totals["item_count"]),
            "total_bytes": int(totals["total_bytes"]),
            "categories": [dict(row) for row in categories],
        }

    def recording_subtypes(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT subtype, COUNT(*) AS count,
                       COALESCE(SUM(size_bytes), 0) AS bytes
                  FROM archive_items
                 WHERE category='recordings' AND subtype<>''
                 GROUP BY subtype
                 ORDER BY subtype
                """
            ).fetchall()
        return [dict(row) for row in rows]
