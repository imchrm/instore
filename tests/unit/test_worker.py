"""Тесты воркера: очередь, восстановление после рестарта, планировщик."""

from __future__ import annotations

import asyncio

from port_fakes import FakeEventBus, FakeJobRepository, FakeStorage
from stories_backend.application.config import ProcessingLimits
from stories_backend.application.use_cases.cleanup_expired import CleanupExpiredUseCase
from stories_backend.application.use_cases.recover_interrupted import RecoverInterruptedUseCase
from stories_backend.domain.entities import Job
from stories_backend.domain.enums import ErrorCode, JobStatus, StoriesFit
from stories_backend.worker.queue import JobQueue
from stories_backend.worker.scheduler import PeriodicCleanupScheduler


class RecordingProcessor:
    """Заглушка ``JobProcessorPort``, фиксирующая обработанные id."""

    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, job_id: str) -> None:
        self.executed.append(job_id)


class GatedProcessor:
    """Обработчик, удерживаемый событием; считает пиковую параллельность."""

    def __init__(self, gate: asyncio.Event) -> None:
        self._gate = gate
        self.active = 0
        self.max_active = 0

    async def execute(self, job_id: str) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await self._gate.wait()
        self.active -= 1


def make_job(job_id: str, *, status: JobStatus, updated_at: float = 0.0) -> Job:
    return Job(
        job_id=job_id,
        key_id="phone",
        url="https://example.com/v",
        segment_time=45,
        max_height=1080,
        stories_fit=StoriesFit.NONE,
        use_cookies=False,
        status=status,
        updated_at=updated_at,
    )


# --- JobQueue --------------------------------------------------------------


async def test_queue_processes_submitted_jobs_in_order() -> None:
    processor = RecordingProcessor()
    queue = JobQueue(processor, max_concurrent_jobs=1)
    await queue.start()

    await queue.submit("a")
    await queue.submit("b")
    await queue.join()
    await queue.stop()

    assert processor.executed == ["a", "b"]


async def test_queue_respects_max_concurrency() -> None:
    gate = asyncio.Event()
    processor = GatedProcessor(gate)
    queue = JobQueue(processor, max_concurrent_jobs=2)
    await queue.start()

    for index in range(4):
        await queue.submit(str(index))

    # Дать потребителю запустить ровно две обработки (остальные ждут семафор).
    for _ in range(100):
        if processor.active == 2:
            break
        await asyncio.sleep(0)
    assert processor.active == 2

    gate.set()
    await queue.join()
    await queue.stop()

    assert processor.max_active == 2


# --- RecoverInterruptedUseCase --------------------------------------------


async def test_recover_marks_only_inflight_jobs() -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    await repo.add(make_job("queued", status=JobStatus.QUEUED))
    await repo.add(make_job("downloading", status=JobStatus.DOWNLOADING))
    await repo.add(make_job("ready", status=JobStatus.READY))
    await repo.add(make_job("failed", status=JobStatus.FAILED))
    use_case = RecoverInterruptedUseCase(repo, bus, clock=lambda: 42.0)

    recovered = await use_case.execute()

    assert set(recovered) == {"queued", "downloading"}
    assert repo.jobs["queued"].status is JobStatus.FAILED
    assert repo.jobs["queued"].error_code is ErrorCode.INTERNAL
    assert repo.jobs["queued"].updated_at == 42.0
    assert repo.jobs["ready"].status is JobStatus.READY
    assert repo.jobs["failed"].status is JobStatus.FAILED
    assert {job_id for job_id, _event in bus.published} == {"queued", "downloading"}


# --- PeriodicCleanupScheduler ---------------------------------------------


async def test_scheduler_run_once_cleans_expired() -> None:
    repo = FakeJobRepository()
    storage = FakeStorage()
    bus = FakeEventBus()
    now = 10_000.0
    await repo.add(make_job("stale", status=JobStatus.READY, updated_at=now - 5000.0))
    cleanup = CleanupExpiredUseCase(
        repo,
        storage,
        bus,
        ProcessingLimits(job_ttl_seconds=1200),
        clock=lambda: now,
    )
    scheduler = PeriodicCleanupScheduler(cleanup, interval_sec=60.0)

    cleaned = await scheduler.run_once()

    assert cleaned == ["stale"]
    assert repo.jobs["stale"].status is JobStatus.EXPIRED


async def test_scheduler_start_stop_is_safe() -> None:
    repo = FakeJobRepository()
    cleanup = CleanupExpiredUseCase(
        repo, FakeStorage(), FakeEventBus(), ProcessingLimits(), clock=lambda: 0.0
    )
    scheduler = PeriodicCleanupScheduler(cleanup, interval_sec=60.0)

    await scheduler.start()
    await scheduler.start()  # идемпотентно
    await scheduler.stop()
    await scheduler.stop()  # повторная остановка безопасна
