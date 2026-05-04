import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

STAGE_QUEUED = "queued"
STAGE_INGEST = "ingest"
STAGE_SCRIPT = "script"
STAGE_AUDIO = "audio"
STAGE_PUBLISH = "publish"
STAGE_DONE = "done"


@dataclass(frozen=True)
class Job:
    id: str
    owner_id: str
    status: str
    stage: str
    title: str
    urls_json: str
    result_json: str
    error: str
    created_at: str
    updated_at: str
    started_at: str
    finished_at: str


@dataclass(frozen=True)
class JobEvent:
    id: int
    job_id: str
    stage: str
    status: str
    message: str
    created_at: str


class JobRepo:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def init(self) -> None:
        if self.path.parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS jobs (
                    id           TEXT PRIMARY KEY,
                    owner_id     TEXT NOT NULL,
                    status       TEXT NOT NULL,
                    stage        TEXT NOT NULL,
                    title        TEXT,
                    urls_json    TEXT NOT NULL,
                    result_json  TEXT,
                    error        TEXT,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL,
                    started_at   TEXT,
                    finished_at  TEXT
                );

                CREATE INDEX IF NOT EXISTS jobs_owner_created_idx ON jobs(owner_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS jobs_status_created_idx ON jobs(status, created_at ASC);

                CREATE TABLE IF NOT EXISTS job_events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id     TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    stage      TEXT NOT NULL,
                    status     TEXT NOT NULL,
                    message    TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS job_events_job_id_idx ON job_events(job_id, created_at ASC);
                """
            )

    def create_job(
        self, *, job_id: str, owner_id: str, title: str, urls_json: str
    ) -> Job:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, owner_id, status, stage, title, urls_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    owner_id,
                    STATUS_QUEUED,
                    STAGE_QUEUED,
                    _nullable(title),
                    urls_json,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO job_events (job_id, stage, status, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, STAGE_QUEUED, STATUS_QUEUED, "job queued", now),
            )
        return self.get_job(job_id, owner_id)

    def get_job(self, job_id: str, owner_id: str) -> Job:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, owner_id, status, stage, title, urls_json, result_json, error,
                       created_at, updated_at, started_at, finished_at
                FROM jobs WHERE id = ? AND owner_id = ?
                """,
                (job_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _job(row)

    def list_jobs(self, owner_id: str, limit: int = 50) -> list[Job]:
        if limit <= 0 or limit > 100:
            limit = 50
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, owner_id, status, stage, title, urls_json, result_json, error,
                       created_at, updated_at, started_at, finished_at
                FROM jobs WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?
                """,
                (owner_id, limit),
            ).fetchall()
        return [_job(row) for row in rows]

    def list_events(self, job_id: str) -> list[JobEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, job_id, stage, status, message, created_at
                FROM job_events WHERE job_id = ? ORDER BY created_at ASC, id ASC
                """,
                (job_id,),
            ).fetchall()
        return [_event(row) for row in rows]

    def claim_next_queued(self) -> Job | None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT id, owner_id, status, stage, title, urls_json, result_json, error,
                       created_at, updated_at, started_at, finished_at
                FROM jobs WHERE status = ? ORDER BY created_at ASC LIMIT 1
                """,
                (STATUS_QUEUED,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            job = _job(row)
            now = _now()
            updated = conn.execute(
                """
                UPDATE jobs
                SET status = ?, stage = ?, error = NULL,
                    started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    STATUS_RUNNING,
                    STAGE_QUEUED,
                    now,
                    now,
                    job.id,
                    STATUS_QUEUED,
                ),
            )
            if updated.rowcount == 0:
                conn.commit()
                return None
            conn.execute(
                """
                INSERT INTO job_events (job_id, stage, status, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job.id, STAGE_QUEUED, STATUS_RUNNING, "job started", now),
            )
            conn.commit()
            return Job(
                **{
                    **job.__dict__,
                    "status": STATUS_RUNNING,
                    "stage": STAGE_QUEUED,
                    "updated_at": now,
                    "started_at": job.started_at or now,
                }
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def set_running_stage(self, job_id: str, stage: str, message: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET status = ?, stage = ?, error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (STATUS_RUNNING, stage, now, job_id),
            )
            conn.execute(
                """
                INSERT INTO job_events (job_id, stage, status, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, stage, STATUS_RUNNING, _nullable(message), now),
            )

    def set_succeeded(self, job_id: str, result_json: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, stage = ?, result_json = ?, error = NULL, updated_at = ?, finished_at = ?
                WHERE id = ?
                """,
                (STATUS_SUCCEEDED, STAGE_DONE, result_json, now, now, job_id),
            )
            conn.execute(
                """
                INSERT INTO job_events (job_id, stage, status, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, STAGE_DONE, STATUS_SUCCEEDED, "job succeeded", now),
            )

    def set_failed(self, job_id: str, stage: str, message: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET status = ?, stage = ?, error = ?, updated_at = ?, finished_at = ?
                WHERE id = ?
                """,
                (STATUS_FAILED, stage, message, now, now, job_id),
            )
            conn.execute(
                """
                INSERT INTO job_events (job_id, stage, status, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, stage, STATUS_FAILED, message, now),
            )

    def retry_job(self, job_id: str, owner_id: str) -> Job:
        job = self.get_job(job_id, owner_id)
        if job.status in {STATUS_RUNNING, STATUS_QUEUED}:
            return job
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, stage = ?, result_json = NULL, error = NULL,
                    updated_at = ?, started_at = NULL, finished_at = NULL
                WHERE id = ? AND owner_id = ?
                """,
                (STATUS_QUEUED, STAGE_QUEUED, now, job_id, owner_id),
            )
            conn.execute(
                """
                INSERT INTO job_events (job_id, stage, status, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, STAGE_QUEUED, STATUS_QUEUED, "job retried", now),
            )
        return self.get_job(job_id, owner_id)

    def reset_running_to_queued(self) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id, stage FROM jobs WHERE status = ?",
                (STATUS_RUNNING,),
            ).fetchall()
            now = _now()
            for row in rows:
                job_id = row["id"]
                stage = row["stage"]
                if stage == STAGE_PUBLISH:
                    message = "job outcome unknown after restart during publish; retry may duplicate the episode"
                    conn.execute(
                        """
                        UPDATE jobs SET status = ?, error = ?, updated_at = ?, finished_at = ?
                        WHERE id = ? AND status = ?
                        """,
                        (STATUS_FAILED, message, now, now, job_id, STATUS_RUNNING),
                    )
                    conn.execute(
                        """
                        INSERT INTO job_events (job_id, stage, status, message, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (job_id, stage, STATUS_FAILED, message, now),
                    )
                    continue
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = ?, stage = ?, error = NULL, updated_at = ?,
                        started_at = NULL, finished_at = NULL
                    WHERE id = ? AND status = ?
                    """,
                    (STATUS_QUEUED, STAGE_QUEUED, now, job_id, STATUS_RUNNING),
                )
                conn.execute(
                    """
                    INSERT INTO job_events (job_id, stage, status, message, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        STAGE_QUEUED,
                        STATUS_QUEUED,
                        "job reset to queued after restart",
                        now,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def job_request_json(urls: list[str], title: str | None) -> str:
    payload: dict[str, Any] = {"urls": urls}
    if title:
        payload["title"] = title
    return json.dumps(payload, separators=(",", ":"))


def _job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        owner_id=row["owner_id"],
        status=row["status"],
        stage=row["stage"],
        title=row["title"] or "",
        urls_json=row["urls_json"],
        result_json=row["result_json"] or "",
        error=row["error"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"] or "",
        finished_at=row["finished_at"] or "",
    )


def _event(row: sqlite3.Row) -> JobEvent:
    return JobEvent(
        id=row["id"],
        job_id=row["job_id"],
        stage=row["stage"],
        status=row["status"],
        message=row["message"] or "",
        created_at=row["created_at"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _nullable(value: str) -> str | None:
    return value or None
