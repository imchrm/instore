"""Тесты репозитория задач на SQLite."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from stories_backend.domain.entities import Chunk, Job, VideoMeta
from stories_backend.domain.enums import ErrorCode, JobStatus, StoriesFit
from stories_backend.infrastructure.persistence.sqlite_repo import SqliteJobRepository


@pytest.fixture
async def repo(tmp_path: Path) -> AsyncIterator[SqliteJobRepository]:
    repository = await SqliteJobRepository.connect(tmp_path / "jobs.sqlite3")
    try:
        yield repository
    finally:
        await repository.close()


def make_job(job_id: str, *, status: JobStatus = JobStatus.QUEUED, updated_at: float = 0.0) -> Job:
    return Job(
        job_id=job_id,
        key_id="phone",
        url="https://example.com/video",
        segment_time=45,
        max_height=1080,
        stories_fit=StoriesFit.COVER,
        use_cookies=True,
        status=status,
        progress=0.25,
        meta=VideoMeta(title="clip", duration_sec=42.0, filesize_bytes=1000, height=1080),
        chunks=[
            Chunk(
                index=0,
                filename="conv_000.mp4",
                duration_sec=45.0,
                size_bytes=10,
                sha256="ab",
                over_limit=False,
            )
        ],
        created_at=1.0,
        updated_at=updated_at,
    )


async def test_add_and_get_roundtrip(repo: SqliteJobRepository) -> None:
    job = make_job("job-1")

    await repo.add(job)
    loaded = await repo.get("job-1")

    assert loaded == job


async def test_get_missing_returns_none(repo: SqliteJobRepository) -> None:
    assert await repo.get("absent") is None


async def test_roundtrip_with_null_meta(repo: SqliteJobRepository) -> None:
    job = make_job("job-1")
    job.meta = None
    job.chunks = []

    await repo.add(job)
    loaded = await repo.get("job-1")

    assert loaded is not None
    assert loaded.meta is None
    assert loaded.chunks == []


async def test_update_persists_changes(repo: SqliteJobRepository) -> None:
    job = make_job("job-1")
    await repo.add(job)

    job.status = JobStatus.FAILED
    job.error_code = ErrorCode.TOO_LARGE
    job.error_message = "слишком большой"
    job.progress = 1.0
    await repo.update(job)

    loaded = await repo.get("job-1")
    assert loaded is not None
    assert loaded.status is JobStatus.FAILED
    assert loaded.error_code is ErrorCode.TOO_LARGE
    assert loaded.error_message == "слишком большой"
    assert loaded.progress == 1.0


async def test_delete_removes_job(repo: SqliteJobRepository) -> None:
    await repo.add(make_job("job-1"))

    await repo.delete("job-1")

    assert await repo.get("job-1") is None


async def test_list_expired_selects_only_stale_ready(repo: SqliteJobRepository) -> None:
    now = time.time()
    await repo.add(make_job("stale", status=JobStatus.READY, updated_at=now - 10_000))
    await repo.add(make_job("fresh", status=JobStatus.READY, updated_at=now))
    await repo.add(make_job("failed-old", status=JobStatus.FAILED, updated_at=now - 10_000))

    expired = await repo.list_expired(ttl_seconds=1200)

    assert [job.job_id for job in expired] == ["stale"]
