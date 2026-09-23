"""Тесты сценариев application на fake-портах."""

from __future__ import annotations

import time

from port_fakes import (
    FakeCookiesStore,
    FakeEventBus,
    FakeJobRepository,
    FakeJobSubmitter,
    FakeStorage,
)
from stories_backend.application.config import ProcessingLimits
from stories_backend.application.use_cases.cleanup_expired import CleanupExpiredUseCase
from stories_backend.application.use_cases.cookies_admin import CookiesAdminUseCase
from stories_backend.application.use_cases.create_job import CreateJobCommand, CreateJobUseCase
from stories_backend.application.use_cases.delete_job import DeleteJobUseCase
from stories_backend.application.use_cases.get_job import GetJobUseCase
from stories_backend.application.use_cases.stream_progress import StreamProgressUseCase
from stories_backend.domain.entities import Job
from stories_backend.domain.enums import JobStatus, StoriesFit


def make_command(key_id: str = "phone") -> CreateJobCommand:
    return CreateJobCommand(
        key_id=key_id,
        url="https://example.com/v",
        segment_time=45,
        max_height=1080,
        stories_fit=StoriesFit.NONE,
        use_cookies=False,
    )


def make_job(job_id: str, key_id: str, *, status: JobStatus, updated_at: float = 0.0) -> Job:
    return Job(
        job_id=job_id,
        key_id=key_id,
        url="https://example.com/v",
        segment_time=45,
        max_height=1080,
        stories_fit=StoriesFit.NONE,
        use_cookies=False,
        status=status,
        updated_at=updated_at,
    )


# --- create_job ------------------------------------------------------------


async def test_create_job_registers_and_enqueues() -> None:
    repo = FakeJobRepository()
    submitter = FakeJobSubmitter()
    use_case = CreateJobUseCase(
        repo,
        submitter,
        clock=lambda: 100.0,
        id_generator=lambda: "job-1",
    )

    job = await use_case.execute(make_command())

    assert job.job_id == "job-1"
    assert job.status is JobStatus.QUEUED
    assert job.created_at == 100.0
    assert job.updated_at == 100.0
    assert repo.jobs["job-1"] is job
    assert submitter.submitted == ["job-1"]


# --- get_job ---------------------------------------------------------------


async def test_get_job_returns_own_job() -> None:
    repo = FakeJobRepository()
    job = make_job("job-1", "phone", status=JobStatus.READY)
    await repo.add(job)
    use_case = GetJobUseCase(repo)

    assert await use_case.execute("job-1", "phone") is job


async def test_get_job_hides_foreign_job() -> None:
    repo = FakeJobRepository()
    await repo.add(make_job("job-1", "phone", status=JobStatus.READY))
    use_case = GetJobUseCase(repo)

    assert await use_case.execute("job-1", "tablet") is None
    assert await use_case.execute("absent", "phone") is None


# --- delete_job ------------------------------------------------------------


async def test_delete_job_removes_own_job() -> None:
    repo = FakeJobRepository()
    storage = FakeStorage()
    await repo.add(make_job("job-1", "phone", status=JobStatus.READY))
    use_case = DeleteJobUseCase(repo, storage)

    assert await use_case.execute("job-1", "phone") is True
    assert storage.removed_jobs == ["job-1"]
    assert "job-1" not in repo.jobs


async def test_delete_job_refuses_foreign_job() -> None:
    repo = FakeJobRepository()
    storage = FakeStorage()
    await repo.add(make_job("job-1", "phone", status=JobStatus.READY))
    use_case = DeleteJobUseCase(repo, storage)

    assert await use_case.execute("job-1", "tablet") is False
    assert storage.removed_jobs == []
    assert "job-1" in repo.jobs


# --- stream_progress -------------------------------------------------------


async def test_stream_progress_subscribes_for_own_job() -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    await repo.add(make_job("job-1", "phone", status=JobStatus.DOWNLOADING))
    use_case = StreamProgressUseCase(repo, bus)

    stream = await use_case.execute("job-1", "phone")

    assert stream is not None
    assert bus.subscribed == ["job-1"]


async def test_stream_progress_forbidden_returns_none() -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    await repo.add(make_job("job-1", "phone", status=JobStatus.DOWNLOADING))
    use_case = StreamProgressUseCase(repo, bus)

    assert await use_case.execute("job-1", "tablet") is None
    assert bus.subscribed == []


# --- cleanup_expired -------------------------------------------------------


async def test_cleanup_expired_marks_and_removes() -> None:
    repo = FakeJobRepository()
    storage = FakeStorage()
    bus = FakeEventBus()
    now = time.time()
    await repo.add(make_job("stale", "phone", status=JobStatus.READY, updated_at=now - 10_000))
    await repo.add(make_job("fresh", "phone", status=JobStatus.READY, updated_at=now))
    use_case = CleanupExpiredUseCase(
        repo,
        storage,
        bus,
        ProcessingLimits(job_ttl_seconds=1200),
        clock=lambda: 500.0,
    )

    cleaned = await use_case.execute()

    assert cleaned == ["stale"]
    assert repo.jobs["stale"].status is JobStatus.EXPIRED
    assert repo.jobs["stale"].updated_at == 500.0
    assert storage.removed_jobs == ["stale"]
    assert repo.jobs["fresh"].status is JobStatus.READY
    assert [job_id for job_id, _event in bus.published] == ["stale"]


# --- cookies_admin ---------------------------------------------------------


async def test_cookies_admin_upload_status_delete() -> None:
    store = FakeCookiesStore()
    use_case = CookiesAdminUseCase(store)

    assert (await use_case.status("phone")).present is False

    await use_case.upload("phone", b"cookie")
    assert store.saved["phone"] == b"cookie"
    assert (await use_case.status("phone")).present is True

    await use_case.delete("phone")
    assert store.deleted == ["phone"]
    assert (await use_case.status("phone")).present is False
