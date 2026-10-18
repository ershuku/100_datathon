"""SQLite job store. One connection guarded by a lock; WAL so readers never block the worker."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

QUEUED, PROCESSING, DONE, FAILED = "queued", "processing", "done", "failed"
ACTIVE_STATUSES = (QUEUED, PROCESSING)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    stage         TEXT NOT NULL DEFAULT 'queued',
    stage_text    TEXT NOT NULL DEFAULT '',
    progress      INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    error_code    TEXT,
    created_at    REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL,
    video_meta    TEXT,
    result        TEXT,
    files_deleted INTEGER NOT NULL DEFAULT 0,
    source        TEXT NOT NULL DEFAULT 'api'
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

_UPDATABLE = {
    "status", "stage", "stage_text", "progress", "error", "error_code",
    "started_at", "finished_at", "video_meta", "result", "files_deleted",
}  # fmt: skip
_JSON_FIELDS = {"video_meta", "result"}


@dataclass(frozen=True)
class JobRecord:
    id: str
    status: str
    stage: str
    stage_text: str
    progress: int
    error: str | None
    error_code: str | None
    created_at: float
    started_at: float | None
    finished_at: float | None
    video_meta: dict[str, Any] | None
    result: dict[str, Any] | None
    files_deleted: bool
    source: str = "api"

    @property
    def queue_wait_sec(self) -> float | None:
        return None if self.started_at is None else self.started_at - self.created_at

    @property
    def processing_sec(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    @property
    def total_sec(self) -> float | None:
        return None if self.finished_at is None else self.finished_at - self.created_at


def _row_to_record(row: sqlite3.Row) -> JobRecord:
    data = dict(row)
    for key in _JSON_FIELDS:
        data[key] = json.loads(data[key]) if data[key] else None
    data["files_deleted"] = bool(data["files_deleted"])
    return JobRecord(**data)


class JobStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            columns = {r[1] for r in self._conn.execute("PRAGMA table_info(jobs)")}
            if "source" not in columns:  # DB created by an older version
                self._conn.execute("ALTER TABLE jobs ADD COLUMN source TEXT NOT NULL DEFAULT 'api'")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create(self, job_id: str, created_at: float, video_meta: dict[str, Any], source: str = "api") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, status, created_at, video_meta, stage_text, source) VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, QUEUED, created_at, json.dumps(video_meta), "В очереди", source),
            )

    def claim(self, job_id: str, started_at: float) -> bool:
        """queued -> processing atomically; False if someone else (e.g. the expiry sweep) got there first."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE jobs SET status = ?, started_at = ? WHERE id = ? AND status = ?",
                (PROCESSING, started_at, job_id, QUEUED),
            )
        return cur.rowcount == 1

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_record(row) if row else None

    def update(self, job_id: str, **fields: Any) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update fields: {sorted(unknown)}")
        values = [json.dumps(v, ensure_ascii=False) if k in _JSON_FIELDS and v is not None else v
                  for k, v in fields.items()]  # fmt: skip
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*values, job_id))  # noqa: S608

    def count_active(self, source: str | None = None) -> int:
        sql, args = "SELECT COUNT(*) FROM jobs WHERE status IN (?, ?)", list(ACTIVE_STATUSES)
        if source is not None:
            sql, args = sql + " AND source = ?", [*args, source]
        with self._lock:
            row = self._conn.execute(sql, args).fetchone()
        return int(row[0])

    def fail_expired_queued(self, created_before: float, finished_at: float) -> list[str]:
        """Queued jobs whose whole budget is gone: answer them now instead of when a slot frees up."""
        with self._lock:
            ids = [r[0] for r in self._conn.execute(
                "SELECT id FROM jobs WHERE status = ? AND created_at <= ?", (QUEUED, created_before)).fetchall()]  # fmt: skip
            self._conn.execute(
                "UPDATE jobs SET status = ?, error = 'timeout', error_code = 'timeout', finished_at = ?, "
                "stage = 'failed', stage_text = 'Ошибка' WHERE status = ? AND created_at <= ?",
                (FAILED, finished_at, QUEUED, created_before),
            )
        return ids

    def fail_interrupted(self, finished_at: float) -> list[str]:
        """On startup: jobs left queued/processing by a previous run can never finish."""
        with self._lock:
            ids = [r[0] for r in self._conn.execute(
                "SELECT id FROM jobs WHERE status IN (?, ?)", ACTIVE_STATUSES).fetchall()]  # fmt: skip
            self._conn.execute(
                "UPDATE jobs SET status = ?, error = ?, error_code = ?, finished_at = ?, stage = 'failed' "
                "WHERE status IN (?, ?)",
                (FAILED, "interrupted by service restart", "interrupted", finished_at, *ACTIVE_STATUSES),
            )
        return ids

    def expired_file_jobs(self, finished_before: float) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM jobs WHERE files_deleted = 0 AND finished_at IS NOT NULL AND finished_at <= ?",
                (finished_before,),
            ).fetchall()
        return [r[0] for r in rows]
