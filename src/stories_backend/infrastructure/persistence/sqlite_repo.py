"""Персистентность задач на SQLite через ``aiosqlite`` (реализация ``JobRepositoryPort``)."""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

from stories_backend.domain.entities import Chunk, Job, VideoMeta
from stories_backend.domain.enums import ErrorCode, JobStatus, StoriesFit

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id        TEXT PRIMARY KEY,
    key_id        TEXT NOT NULL,
    url           TEXT NOT NULL,
    segment_time  INTEGER NOT NULL,
    max_height    INTEGER NOT NULL,
    stories_fit   TEXT NOT NULL,
    use_cookies   INTEGER NOT NULL,
    status        TEXT NOT NULL,
    progress      REAL NOT NULL,
    meta          TEXT,
    chunks        TEXT NOT NULL,
    error_code    TEXT,
    error_message TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_updated ON jobs (status, updated_at);
"""

_COLUMNS = (
    "job_id",
    "key_id",
    "url",
    "segment_time",
    "max_height",
    "stories_fit",
    "use_cookies",
    "status",
    "progress",
    "meta",
    "chunks",
    "error_code",
    "error_message",
    "created_at",
    "updated_at",
)


def _meta_to_json(meta: VideoMeta | None) -> str | None:
    return None if meta is None else json.dumps(dataclasses.asdict(meta))


def _meta_from_json(raw: str | None) -> VideoMeta | None:
    if raw is None:
        return None
    data: dict[str, Any] = json.loads(raw)
    return VideoMeta(**data)


def _chunks_to_json(chunks: list[Chunk]) -> str:
    return json.dumps([dataclasses.asdict(chunk) for chunk in chunks])


def _chunks_from_json(raw: str) -> list[Chunk]:
    items: list[dict[str, Any]] = json.loads(raw)
    return [Chunk(**item) for item in items]


class SqliteJobRepository:
    """Репозиторий задач поверх одного соединения ``aiosqlite``."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    @classmethod
    async def connect(cls, db_path: str | Path) -> SqliteJobRepository:
        """Открыть БД, применить схему и вернуть готовый репозиторий."""
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(path))
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        """Закрыть соединение с БД."""
        await self._conn.close()

    async def add(self, job: Job) -> None:
        placeholders = ", ".join(["?"] * len(_COLUMNS))
        columns = ", ".join(_COLUMNS)
        await self._conn.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
            self._to_params(job),
        )
        await self._conn.commit()

    async def get(self, job_id: str) -> Job | None:
        cursor = await self._conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return None if row is None else self._from_row(row)

    async def update(self, job: Job) -> None:
        # _COLUMNS[0] == "job_id", а порядок _to_params совпадает с _COLUMNS.
        assignments = ", ".join(f"{column} = ?" for column in _COLUMNS[1:])
        values = self._to_params(job)
        await self._conn.execute(
            f"UPDATE jobs SET {assignments} WHERE job_id = ?",
            (*values[1:], job.job_id),
        )
        await self._conn.commit()

    async def delete(self, job_id: str) -> None:
        await self._conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        await self._conn.commit()

    async def list_expired(self, ttl_seconds: int) -> list[Job]:
        """Вернуть готовые задачи, у которых с момента готовности прошло больше ``ttl_seconds``."""
        threshold = time.time() - ttl_seconds
        cursor = await self._conn.execute(
            "SELECT * FROM jobs WHERE status = ? AND updated_at <= ?",
            (JobStatus.READY.value, threshold),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [self._from_row(row) for row in rows]

    async def list_unfinished(self) -> list[Job]:
        """Вернуть задачи в незавершённых статусах (не ready/failed/expired)."""
        terminal = (JobStatus.READY.value, JobStatus.FAILED.value, JobStatus.EXPIRED.value)
        placeholders = ", ".join(["?"] * len(terminal))
        cursor = await self._conn.execute(
            f"SELECT * FROM jobs WHERE status NOT IN ({placeholders})",
            terminal,
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _to_params(job: Job) -> tuple[Any, ...]:
        return (
            job.job_id,
            job.key_id,
            job.url,
            job.segment_time,
            job.max_height,
            job.stories_fit.value,
            int(job.use_cookies),
            job.status.value,
            job.progress,
            _meta_to_json(job.meta),
            _chunks_to_json(job.chunks),
            None if job.error_code is None else job.error_code.value,
            job.error_message,
            job.created_at,
            job.updated_at,
        )

    @staticmethod
    def _from_row(row: aiosqlite.Row) -> Job:
        error_code_raw: str | None = row["error_code"]
        return Job(
            job_id=row["job_id"],
            key_id=row["key_id"],
            url=row["url"],
            segment_time=row["segment_time"],
            max_height=row["max_height"],
            stories_fit=StoriesFit(row["stories_fit"]),
            use_cookies=bool(row["use_cookies"]),
            status=JobStatus(row["status"]),
            progress=row["progress"],
            meta=_meta_from_json(row["meta"]),
            chunks=_chunks_from_json(row["chunks"]),
            error_code=None if error_code_raw is None else ErrorCode(error_code_raw),
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
