from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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

    @staticmethod
    def _recording_source_parts(
        source_key: str,
    ) -> tuple[str, str, int | None]:
        vehicle_identity, marker, remainder = source_key.partition(":recording:")
        if not marker or not vehicle_identity:
            return "", "", None
        filename, timestamp_marker, raw_timestamp = remainder.rpartition(":")
        if not timestamp_marker:
            filename = remainder
            raw_timestamp = ""
        try:
            timestamp = int(raw_timestamp) if raw_timestamp else None
        except (TypeError, ValueError, OverflowError):
            timestamp = None
        return vehicle_identity, filename[:255], timestamp

    @staticmethod
    def _recording_subtype_hint(
        item: dict[str, Any], filename: str, fallback: str = ""
    ) -> str:
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
        lower_name = filename.casefold()
        if lower_name.startswith("replay_"):
            return "replay"
        if lower_name.startswith("dvr_"):
            return "oem_dashcam"
        if lower_name.startswith("event_"):
            return "surveillance"
        if lower_name.startswith("proximity_"):
            return "proximity"
        if source_type == "normal" or lower_name.startswith("cam"):
            return "drive"
        return fallback[:40]

    @classmethod
    def _backfill_retention_tombstones(
        cls, conn: sqlite3.Connection
    ) -> None:
        conn.execute(
            """
            UPDATE archive_retention_tombstones
               SET last_seen_at=deleted_at
             WHERE last_seen_at IS NULL
            """
        )
        rows = conn.execute(
            """
            SELECT source_key,vehicle_identity,filename,subtype,
                   source_timestamp
              FROM archive_retention_tombstones
             WHERE category='recordings'
            """
        ).fetchall()
        for row in rows:
            identity, filename, timestamp = cls._recording_source_parts(
                str(row["source_key"])
            )
            current_filename = str(row["filename"] or "")
            current_subtype = str(row["subtype"] or "")
            conn.execute(
                """
                UPDATE archive_retention_tombstones
                   SET vehicle_identity=?,filename=?,subtype=?,
                       source_timestamp=COALESCE(source_timestamp,?)
                 WHERE source_key=?
                """,
                (
                    str(row["vehicle_identity"] or "") or identity,
                    current_filename or filename,
                    current_subtype
                    or cls._recording_subtype_hint({}, current_filename or filename),
                    timestamp,
                    str(row["source_key"]),
                ),
            )

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

                CREATE TABLE IF NOT EXISTS archive_retention_tombstones (
                    source_key TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    deleted_at TEXT NOT NULL,
                    vehicle_identity TEXT NOT NULL DEFAULT '',
                    vehicle TEXT NOT NULL DEFAULT '',
                    filename TEXT NOT NULL DEFAULT '',
                    subtype TEXT NOT NULL DEFAULT '',
                    source_timestamp INTEGER,
                    remote_size_bytes INTEGER NOT NULL DEFAULT 0,
                    item_json TEXT NOT NULL DEFAULT '{}',
                    last_seen_at TEXT,
                    restore_requested_at TEXT
                );

                CREATE TABLE IF NOT EXISTS archive_retention_protections (
                    source_key TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    protected_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS archive_retention_deletion_jobs (
                    item_id INTEGER PRIMARY KEY,
                    source_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    original_relative_path TEXT NOT NULL,
                    staged_relative_path TEXT NOT NULL,
                    prepared_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recording_download_jobs (
                    source_key TEXT PRIMARY KEY,
                    vehicle_identity TEXT NOT NULL,
                    item_json TEXT NOT NULL,
                    partial_relative_path TEXT NOT NULL DEFAULT '',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recording_download_jobs_vehicle
                    ON recording_download_jobs(
                        vehicle_identity, first_seen_at, source_key
                    );

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
            tombstone_columns = {
                str(row["name"])
                for row in conn.execute(
                    "PRAGMA table_info(archive_retention_tombstones)"
                ).fetchall()
            }
            tombstone_migrations = {
                "vehicle_identity": (
                    "TEXT NOT NULL DEFAULT ''"
                ),
                "vehicle": "TEXT NOT NULL DEFAULT ''",
                "filename": "TEXT NOT NULL DEFAULT ''",
                "subtype": "TEXT NOT NULL DEFAULT ''",
                "source_timestamp": "INTEGER",
                "remote_size_bytes": "INTEGER NOT NULL DEFAULT 0",
                "item_json": "TEXT NOT NULL DEFAULT '{}'",
                "last_seen_at": "TEXT",
                "restore_requested_at": "TEXT",
            }
            for name, declaration in tombstone_migrations.items():
                if name not in tombstone_columns:
                    conn.execute(
                        "ALTER TABLE archive_retention_tombstones "
                        f"ADD COLUMN {name} {declaration}"
                    )
            recording_job_columns = {
                str(row["name"])
                for row in conn.execute(
                    "PRAGMA table_info(recording_download_jobs)"
                ).fetchall()
            }
            if "partial_relative_path" not in recording_job_columns:
                conn.execute(
                    "ALTER TABLE recording_download_jobs ADD COLUMN "
                    "partial_relative_path TEXT NOT NULL DEFAULT ''"
                )
            self._backfill_retention_tombstones(conn)
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
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT (
                    EXISTS(
                        SELECT 1 FROM archive_items WHERE source_key=?
                    ) OR EXISTS(
                        SELECT 1 FROM archive_retention_tombstones
                         WHERE source_key=?
                    )
                ) AS known
                """,
                (source_key, source_key),
            ).fetchone()
        return bool(row["known"]) if row else False

    def is_retention_tombstoned(self, source_key: str) -> bool:
        if not isinstance(source_key, str) or not source_key:
            return False
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM archive_retention_tombstones
                 WHERE source_key=?
                """,
                (source_key,),
            ).fetchone()
        return row is not None

    @staticmethod
    def _recording_job_identity(value: str, label: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text.")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{label} is required.")
        if len(normalized) > 1000 or any(
            ord(character) < 32 for character in normalized
        ):
            raise ValueError(f"{label} is invalid.")
        return normalized

    @staticmethod
    def _recording_partial_path(value: Any, *, allow_empty: bool) -> str:
        if not isinstance(value, str):
            raise ValueError("Recording partial paths must be text.")
        if not value and allow_empty:
            return ""
        partial = Path(value)
        if (
            not value
            or len(value) > 4096
            or partial.is_absolute()
            or ".." in partial.parts
            or len(partial.name) <= len(".part")
            or not partial.name.endswith(".part")
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("Recording partial path is invalid.")
        return value

    @staticmethod
    def _canonical_json_metadata(value: Any) -> str:
        if not isinstance(value, (dict, list)):
            raise ValueError("Metadata must be a JSON object or array.")
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Metadata must contain valid JSON values."
            ) from exc

    @classmethod
    def _canonical_recording_job_json(cls, item: dict[str, Any]) -> str:
        if not isinstance(item, dict):
            raise ValueError("A recording download job item must be a JSON object.")
        try:
            return cls._canonical_json_metadata(item)
        except ValueError as exc:
            raise ValueError(
                "A recording download job item must contain valid JSON values."
            ) from exc

    @classmethod
    def _canonical_stored_metadata(cls, raw_payload: Any) -> str:
        try:
            decoded = json.loads(raw_payload)
            return cls._canonical_json_metadata(decoded)
        except (json.JSONDecodeError, TypeError, ValueError):
            return "{}"

    def remember_recording_download_jobs(
        self,
        vehicle_identity: str,
        jobs: Mapping[str, dict[str, Any]],
        partial_relative_paths: Mapping[str, str] | None = None,
    ) -> set[str]:
        """Remember one discovery batch and return keys known before the batch.

        Serialization is completed before opening the transaction, so one bad
        vehicle item cannot leave a partially remembered discovery batch.
        """
        identity = self._recording_job_identity(
            vehicle_identity, "Vehicle identity"
        )
        if not isinstance(jobs, Mapping):
            raise ValueError("Recording download jobs must be a mapping.")
        if partial_relative_paths is not None and not isinstance(
            partial_relative_paths, Mapping
        ):
            raise ValueError("Recording partial paths must be a mapping.")

        prepared: list[tuple[str, str, str]] = []
        for raw_source_key, item in jobs.items():
            source_key = self._recording_job_identity(raw_source_key, "Source key")
            partial_value: Any = (
                partial_relative_paths.get(raw_source_key, "")
                if partial_relative_paths is not None
                else ""
            )
            partial_value = self._recording_partial_path(
                partial_value, allow_empty=True
            )
            prepared.append(
                (
                    source_key,
                    self._canonical_recording_job_json(item),
                    partial_value,
                )
            )
        if not prepared:
            return set()

        source_keys = {source_key for source_key, _payload, _path in prepared}
        seen_at = utc_now()
        with self.connect() as conn:
            # The preexisting-key snapshot and every upsert are one atomic
            # discovery operation, including when two sync triggers race.
            conn.execute("BEGIN IMMEDIATE")
            existing: dict[str, str] = {}
            ordered_keys = sorted(source_keys)
            for offset in range(0, len(ordered_keys), 500):
                chunk = ordered_keys[offset : offset + 500]
                placeholders = ",".join("?" for _key in chunk)
                rows = conn.execute(
                    f"""
                    SELECT source_key, vehicle_identity
                      FROM recording_download_jobs
                     WHERE source_key IN ({placeholders})
                    """,
                    chunk,
                ).fetchall()
                existing.update(
                    {
                        str(row["source_key"]): str(row["vehicle_identity"])
                        for row in rows
                    }
                )

            mismatched = sorted(
                source_key
                for source_key, stored_identity in existing.items()
                if stored_identity != identity
            )
            if mismatched:
                raise ValueError(
                    "A recording download source key belongs to another vehicle."
                )

            conn.executemany(
                """
                INSERT INTO recording_download_jobs(
                    source_key,vehicle_identity,item_json,partial_relative_path,
                    first_seen_at,last_seen_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(source_key) DO UPDATE SET
                    item_json=excluded.item_json,
                    partial_relative_path=CASE
                        WHEN recording_download_jobs.partial_relative_path=''
                            THEN excluded.partial_relative_path
                        ELSE recording_download_jobs.partial_relative_path
                    END,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    (source_key, identity, payload, partial, seen_at, seen_at)
                    for source_key, payload, partial in prepared
                ),
            )
        return set(existing)

    def list_recording_download_jobs(
        self, vehicle_identity: str
    ) -> list[dict[str, Any]]:
        identity = self._recording_job_identity(
            vehicle_identity, "Vehicle identity"
        )
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT source_key,vehicle_identity,item_json,partial_relative_path,
                       first_seen_at,last_seen_at
                  FROM recording_download_jobs
                 WHERE vehicle_identity=?
                 ORDER BY first_seen_at,source_key
                """,
                (identity,),
            ).fetchall()

        jobs: list[dict[str, Any]] = []
        for row in rows:
            try:
                item = json.loads(row["item_json"])
            except (json.JSONDecodeError, TypeError) as exc:
                raise RuntimeError(
                    "A stored recording download job contains invalid JSON."
                ) from exc
            if not isinstance(item, dict):
                raise RuntimeError(
                    "A stored recording download job is not a JSON object."
                )
            jobs.append(
                {
                    "source_key": str(row["source_key"]),
                    "vehicle_identity": str(row["vehicle_identity"]),
                    "item": item,
                    "partial_relative_path": str(row["partial_relative_path"]),
                    "first_seen_at": str(row["first_seen_at"]),
                    "last_seen_at": str(row["last_seen_at"]),
                }
            )
        return jobs

    def update_recording_download_job_partial_path(
        self, source_key: str, partial_relative_path: str
    ) -> bool:
        normalized = self._recording_job_identity(source_key, "Source key")
        partial = self._recording_partial_path(
            partial_relative_path, allow_empty=False
        )
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE recording_download_jobs
                   SET partial_relative_path=?
                 WHERE source_key=?
                """,
                (partial, normalized),
            )
        return cursor.rowcount == 1

    def delete_recording_download_job(self, source_key: str) -> bool:
        normalized = self._recording_job_identity(source_key, "Source key")
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM recording_download_jobs WHERE source_key=?",
                (normalized,),
            )
        return cursor.rowcount == 1

    def complete_recording_download_job(self, source_key: str) -> bool:
        """Remove a job after its recording has been archived successfully."""
        return self.delete_recording_download_job(source_key)

    def reconcile_recording_tombstones(
        self,
        vehicle_identity: str,
        live_jobs: Mapping[str, dict[str, Any]],
    ) -> dict[str, int]:
        """Reconcile one vehicle after its complete remote listing is known."""
        identity = self._recording_job_identity(
            vehicle_identity, "Vehicle identity"
        )
        if not isinstance(live_jobs, Mapping):
            raise ValueError("Live recording jobs must be a mapping.")

        prepared: dict[str, dict[str, Any]] = {}
        for raw_source_key, item in live_jobs.items():
            source_key = self._recording_job_identity(raw_source_key, "Source key")
            source_identity, key_filename, key_timestamp = (
                self._recording_source_parts(source_key)
            )
            if source_identity != identity:
                raise ValueError(
                    "A live recording source key belongs to another vehicle."
                )
            payload = self._canonical_recording_job_json(item)
            raw_filename = item.get("filename")
            filename = (
                raw_filename.strip()[:255]
                if isinstance(raw_filename, str)
                and raw_filename.strip()
                and all(ord(character) >= 32 for character in raw_filename)
                else key_filename
            )
            timestamp: int | None = key_timestamp
            raw_timestamp = item.get("timestamp")
            if raw_timestamp is not None:
                try:
                    timestamp = int(raw_timestamp)
                except (TypeError, ValueError, OverflowError):
                    timestamp = key_timestamp
            try:
                remote_size = max(
                    0, int(item.get("size") or item.get("size_bytes") or 0)
                )
            except (TypeError, ValueError, OverflowError):
                remote_size = 0
            prepared[source_key] = {
                "item_json": payload,
                "filename": filename,
                "subtype": self._recording_subtype_hint(item, filename),
                "source_timestamp": timestamp,
                "remote_size_bytes": remote_size,
            }

        observed_at = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT source_key,filename,subtype,source_timestamp,
                       remote_size_bytes
                  FROM archive_retention_tombstones
                 WHERE category='recordings' AND vehicle_identity=?
                """,
                (identity,),
            ).fetchall()
            tombstones = {str(row["source_key"]): row for row in rows}
            present_keys = set(tombstones).intersection(prepared)
            missing_keys = set(tombstones).difference(prepared)

            for source_key in sorted(present_keys):
                current = tombstones[source_key]
                incoming = prepared[source_key]
                filename = str(incoming["filename"] or current["filename"] or "")
                subtype = str(
                    incoming["subtype"] or current["subtype"] or ""
                )
                timestamp = incoming["source_timestamp"]
                if timestamp is None:
                    timestamp = current["source_timestamp"]
                remote_size = int(incoming["remote_size_bytes"] or 0)
                if remote_size <= 0:
                    remote_size = max(0, int(current["remote_size_bytes"] or 0))
                conn.execute(
                    """
                    UPDATE archive_retention_tombstones
                       SET filename=?,subtype=?,source_timestamp=?,
                           remote_size_bytes=?,item_json=?,last_seen_at=?
                     WHERE source_key=? AND category='recordings'
                       AND vehicle_identity=?
                    """,
                    (
                        filename,
                        subtype,
                        timestamp,
                        remote_size,
                        str(incoming["item_json"]),
                        observed_at,
                        source_key,
                        identity,
                    ),
                )

            if missing_keys:
                conn.executemany(
                    """
                    DELETE FROM archive_retention_tombstones
                     WHERE source_key=? AND category='recordings'
                       AND vehicle_identity=?
                    """,
                    ((source_key, identity) for source_key in sorted(missing_keys)),
                )

                # A missing tombstone can still have a resumable restore job.
                # Keep the job until SyncEngine has deterministically removed
                # its .part and .part.meta artifacts. The engine deletes the
                # job only after that cleanup succeeds.

        return {"updated": len(present_keys), "purged": len(missing_keys)}

    def list_deleted_recordings(
        self,
        *,
        category: str = "recordings",
        subtype: str = "",
        search: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 250))
        clauses: list[str] = []
        arguments: list[Any] = []
        if category:
            clauses.append("category=?")
            arguments.append(category)
        if subtype:
            clauses.append("subtype=?")
            arguments.append(subtype)
        if search:
            escaped = (
                search.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            clauses.append(
                "(filename LIKE ? ESCAPE '\\' OR vehicle LIKE ? ESCAPE '\\')"
            )
            arguments.extend((f"%{escaped}%", f"%{escaped}%"))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        arguments.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT source_key,category,subtype,vehicle,filename,
                       source_timestamp,0 AS size_bytes,remote_size_bytes,
                       deleted_at,last_seen_at,restore_requested_at
                  FROM archive_retention_tombstones
                  {where}
                 ORDER BY CASE
                     WHEN source_timestamp IS NULL OR source_timestamp<=0
                         THEN CAST(strftime('%s', deleted_at) AS INTEGER) * 1000
                     WHEN source_timestamp<10000000000
                         THEN source_timestamp * 1000
                     ELSE source_timestamp
                 END DESC, source_key
                 LIMIT ?
                """,
                arguments,
            ).fetchall()
        return [dict(row) for row in rows]

    def request_recording_restore(self, source_key: str) -> str | None:
        normalized = self._recording_job_identity(source_key, "Source key")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            tombstone = conn.execute(
                """
                SELECT vehicle_identity
                  FROM archive_retention_tombstones
                 WHERE source_key=? AND category='recordings'
                   AND last_seen_at IS NOT NULL
                """,
                (normalized,),
            ).fetchone()
            if tombstone is None:
                return None
            cursor = conn.execute(
                """
                UPDATE archive_retention_tombstones
                   SET restore_requested_at=COALESCE(restore_requested_at,?)
                 WHERE source_key=? AND category='recordings'
                   AND last_seen_at IS NOT NULL
                """,
                (utc_now(), normalized),
            )
        if cursor.rowcount != 1:
            return None
        return str(tombstone["vehicle_identity"])

    def recording_restore_requested(self, source_key: str) -> bool:
        if not isinstance(source_key, str) or not source_key:
            return False
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM archive_retention_tombstones
                 WHERE source_key=? AND category='recordings'
                   AND restore_requested_at IS NOT NULL
                """,
                (source_key,),
            ).fetchone()
        return row is not None

    def has_pending_recording_restores(self, vehicle_identity: str) -> bool:
        identity = self._recording_job_identity(
            vehicle_identity, "Vehicle identity"
        )
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM archive_retention_tombstones
                 WHERE category='recordings'
                   AND vehicle_identity=?
                   AND restore_requested_at IS NOT NULL
                 LIMIT 1
                """,
                (identity,),
            ).fetchone()
        return row is not None

    def complete_recording_restore(self, source_key: str) -> bool:
        normalized = self._recording_job_identity(source_key, "Source key")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            tombstone = conn.execute(
                """
                SELECT category FROM archive_retention_tombstones
                 WHERE source_key=? AND category='recordings'
                   AND restore_requested_at IS NOT NULL
                """,
                (normalized,),
            ).fetchone()
            if tombstone is None:
                return False
            conn.execute(
                """
                INSERT INTO archive_retention_protections(
                    source_key,category,protected_at
                ) VALUES(?,?,?)
                ON CONFLICT(source_key) DO UPDATE SET
                    category=excluded.category,
                    protected_at=excluded.protected_at
                """,
                (normalized, str(tombstone["category"]), utc_now()),
            )
            cursor = conn.execute(
                "DELETE FROM archive_retention_tombstones WHERE source_key=?",
                (normalized,),
            )
        return cursor.rowcount == 1

    def list_retention_protected_source_keys(
        self, category: str | None = None
    ) -> set[str]:
        normalized_category = category.strip() if isinstance(category, str) else ""
        if category is not None and not isinstance(category, str):
            raise ValueError("Protection category must be text.")
        where = "WHERE category=?" if normalized_category else ""
        parameters: tuple[Any, ...] = (
            (normalized_category,) if normalized_category else ()
        )
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT source_key FROM archive_retention_protections {where}
                """,
                parameters,
            ).fetchall()
        return {str(row["source_key"]) for row in rows}

    def is_retention_protected(self, source_key: str) -> bool:
        if not isinstance(source_key, str) or not source_key:
            return False
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM archive_retention_protections WHERE source_key=?
                """,
                (source_key,),
            ).fetchone()
        return row is not None

    def clear_retention_protection(self, source_key: str) -> bool:
        normalized = self._recording_job_identity(source_key, "Source key")
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM archive_retention_protections WHERE source_key=?",
                (normalized,),
            )
        return cursor.rowcount == 1

    def get_item_by_source_key(self, source_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM archive_items WHERE source_key=?", (source_key,)
            ).fetchone()
        return dict(row) if row else None

    def count_archive_path_references(self, relative_path: str) -> int:
        """Count inventory rows that still depend on one physical path."""
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or len(relative_path) > 4096
            or any(ord(character) < 32 for character in relative_path)
        ):
            raise ValueError("Archive path is invalid.")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM archive_items WHERE relative_path=?",
                (relative_path,),
            ).fetchone()
        return int(row[0])

    def archive_path_has_other_source(
        self, relative_path: str, source_key: str
    ) -> bool:
        """Return whether another inventory identity owns the same path."""
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or len(relative_path) > 4096
            or any(ord(character) < 32 for character in relative_path)
        ):
            raise ValueError("Archive path is invalid.")
        normalized_source = self._recording_job_identity(source_key, "Source key")
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM archive_items
                 WHERE relative_path=? AND source_key<>?
                 LIMIT 1
                """,
                (relative_path, normalized_source),
            ).fetchone()
        return row is not None

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

    def list_retention_candidates(
        self,
        category: str | None = None,
        *,
        include_protected: bool = False,
    ) -> list[dict[str, Any]]:
        """Return archive rows in stable insertion order.

        The engine applies recorded-at time first and falls back to local
        insertion time when the source supplied no usable timestamp. The caller
        remains responsible for deleting files before removing the row. Pinned
        rows are omitted unless ``include_protected`` is requested for ranking.
        """
        normalized_category = ""
        if category is not None:
            if not isinstance(category, str):
                raise ValueError("Retention category must be text.")
            normalized_category = category.strip()

        clauses: list[str] = []
        if not include_protected:
            clauses.append(
                "NOT EXISTS ("
                "SELECT 1 FROM archive_retention_protections AS protection "
                "WHERE protection.source_key=item.source_key)"
            )
        if normalized_category:
            clauses.append("item.category=?")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        parameters: tuple[Any, ...] = (
            (normalized_category,) if normalized_category else ()
        )
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT item.id,item.source_key,item.category,item.subtype,
                       item.vehicle,item.filename,item.relative_path,
                       item.media_type,item.size_bytes,item.sha256,
                       item.source_timestamp,item.metadata_json,item.created_at
                  FROM archive_items AS item
                  {where}
                 ORDER BY item.created_at ASC,item.id ASC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_archive_item(self, item_id: int) -> bool:
        """Atomically replace one unprotected inventory row with a tombstone."""
        if isinstance(item_id, bool):
            return False
        try:
            normalized_id = int(item_id)
        except (TypeError, ValueError, OverflowError):
            return False
        if normalized_id <= 0:
            return False
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            item = conn.execute(
                """
                SELECT item.source_key,item.category,item.vehicle,item.filename,
                       item.subtype,item.source_timestamp,item.size_bytes,
                       item.metadata_json
                  FROM archive_items AS item
                 WHERE item.id=? AND NOT EXISTS (
                       SELECT 1 FROM archive_retention_protections AS protection
                        WHERE protection.source_key=item.source_key
                 )
                """,
                (normalized_id,),
            ).fetchone()
            if item is None:
                return False
            source_key = str(item["source_key"])
            category = str(item["category"])
            identity = (
                self._recording_source_parts(source_key)[0]
                if category == "recordings"
                else ""
            )
            deleted_at = utc_now()
            conn.execute(
                """
                INSERT INTO archive_retention_tombstones(
                    source_key,category,deleted_at,vehicle_identity,vehicle,
                    filename,subtype,source_timestamp,remote_size_bytes,
                    item_json,last_seen_at,restore_requested_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)
                ON CONFLICT(source_key) DO UPDATE SET
                    category=excluded.category,
                    deleted_at=excluded.deleted_at,
                    vehicle_identity=excluded.vehicle_identity,
                    vehicle=excluded.vehicle,
                    filename=excluded.filename,
                    subtype=excluded.subtype,
                    source_timestamp=excluded.source_timestamp,
                    remote_size_bytes=excluded.remote_size_bytes,
                    item_json=excluded.item_json,
                    last_seen_at=excluded.last_seen_at,
                    restore_requested_at=NULL
                """,
                (
                    source_key,
                    category,
                    deleted_at,
                    identity,
                    str(item["vehicle"] or ""),
                    str(item["filename"] or "")[:255],
                    str(item["subtype"] or "")[:40],
                    item["source_timestamp"],
                    max(0, int(item["size_bytes"] or 0)),
                    self._canonical_stored_metadata(item["metadata_json"]),
                    deleted_at,
                ),
            )
            cursor = conn.execute(
                "DELETE FROM archive_items WHERE id=?", (normalized_id,)
            )
        return cursor.rowcount == 1

    def prepare_retention_deletion(
        self,
        item_id: int,
        staged_relative_path: str,
    ) -> dict[str, Any] | None:
        """Persist a file-staging journal before retention moves any bytes."""
        if isinstance(item_id, bool):
            return None
        try:
            normalized_id = int(item_id)
        except (TypeError, ValueError, OverflowError):
            return None
        if not isinstance(staged_relative_path, str):
            return None
        staged = Path(staged_relative_path)
        if (
            normalized_id <= 0
            or not staged_relative_path
            or len(staged_relative_path) > 4096
            or staged.is_absolute()
            or ".." in staged.parts
            or any(ord(character) < 32 for character in staged_relative_path)
        ):
            return None
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            item = conn.execute(
                """
                SELECT id,source_key,category,relative_path
                  FROM archive_items AS item
                 WHERE id=? AND NOT EXISTS (
                       SELECT 1 FROM archive_retention_protections AS protection
                        WHERE protection.source_key=item.source_key
                 )
                """,
                (normalized_id,),
            ).fetchone()
            if item is None:
                return None
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO archive_retention_deletion_jobs(
                    item_id,source_key,category,original_relative_path,
                    staged_relative_path,prepared_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    normalized_id,
                    str(item["source_key"]),
                    str(item["category"]),
                    str(item["relative_path"]),
                    staged_relative_path,
                    utc_now(),
                ),
            )
            if cursor.rowcount != 1:
                return None
        return {
            "item_id": normalized_id,
            "source_key": str(item["source_key"]),
            "category": str(item["category"]),
            "original_relative_path": str(item["relative_path"]),
            "staged_relative_path": staged_relative_path,
        }

    def list_retention_deletion_jobs(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT job.item_id,job.source_key,job.category,
                       job.original_relative_path,
                       job.staged_relative_path,job.prepared_at,
                       EXISTS(
                           SELECT 1 FROM archive_items AS item
                            WHERE item.id=job.item_id
                              AND item.source_key=job.source_key
                       ) AS inventory_present,
                       EXISTS(
                           SELECT 1 FROM archive_retention_tombstones AS tombstone
                            WHERE tombstone.source_key=job.source_key
                       ) AS tombstone_present
                  FROM archive_retention_deletion_jobs AS job
                 ORDER BY job.item_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def finish_retention_deletion(self, item_id: int) -> bool:
        if isinstance(item_id, bool):
            return False
        try:
            normalized_id = int(item_id)
        except (TypeError, ValueError, OverflowError):
            return False
        if normalized_id <= 0:
            return False
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM archive_retention_deletion_jobs WHERE item_id=?",
                (normalized_id,),
            )
        return cursor.rowcount == 1

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
                       size_bytes,sha256,source_timestamp,metadata_json,created_at,
                       EXISTS(
                           SELECT 1 FROM archive_retention_protections AS protection
                            WHERE protection.source_key=archive_items.source_key
                       ) AS retention_protected
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
