"""Общие in-memory реализации портов для тестов сценариев application.

Модуль лежит в корне ``tests`` (добавлен в ``pythonpath``) и импортируется
тестами как ``port_fakes``. Он не собирается pytest (нет префикса ``test_``).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

from stories_backend.domain.entities import CookiesStatus, Job, ProgressEvent
from stories_backend.domain.enums import JobStatus


class FakeJobRepository:
    """In-memory реализация ``JobRepositoryPort``."""

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}

    async def add(self, job: Job) -> None:
        self.jobs[job.job_id] = job

    async def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    async def update(self, job: Job) -> None:
        self.jobs[job.job_id] = job

    async def delete(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)

    async def list_expired(self, ttl_seconds: int) -> list[Job]:
        threshold = time.time() - ttl_seconds
        return [
            job
            for job in self.jobs.values()
            if job.status is JobStatus.READY and job.updated_at <= threshold
        ]


class FakeStorage:
    """Реализация ``StoragePort``, фиксирующая вызовы удаления.

    Если задан ``base_dir``, ``job_dir`` создаёт реальный каталог задачи под ним
    (нужно тестам оркестрации, читающим файлы кусков); иначе возвращает
    виртуальный путь.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir
        self.removed_jobs: list[str] = []
        self.removed_intermediate: list[str] = []

    def job_dir(self, job_id: str) -> str:
        if self._base_dir is None:
            return f"/data/jobs/{job_id}"
        path = self._base_dir / job_id
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    async def remove_job(self, job_id: str) -> None:
        self.removed_jobs.append(job_id)

    async def remove_intermediate(self, job_id: str) -> None:
        self.removed_intermediate.append(job_id)


async def _empty_stream() -> AsyncIterator[ProgressEvent]:
    empty: tuple[ProgressEvent, ...] = ()  # пустой асинхронный поток
    for event in empty:
        yield event


class FakeEventBus:
    """Реализация ``EventBusPort``, фиксирующая публикации и подписки."""

    def __init__(self) -> None:
        self.published: list[tuple[str, ProgressEvent]] = []
        self.subscribed: list[str] = []

    async def publish(self, job_id: str, event: ProgressEvent) -> None:
        self.published.append((job_id, event))

    def subscribe(self, job_id: str) -> AsyncIterator[ProgressEvent]:
        self.subscribed.append(job_id)
        return _empty_stream()


class FakeCookiesStore:
    """In-memory реализация ``CookiesStorePort``."""

    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, key_id: str, content: bytes) -> None:
        self.saved[key_id] = content

    async def path(self, key_id: str) -> str | None:
        return f"/cookies/{key_id}.txt" if key_id in self.saved else None

    async def status(self, key_id: str) -> CookiesStatus:
        return CookiesStatus(present=key_id in self.saved)

    async def delete(self, key_id: str) -> None:
        self.deleted.append(key_id)
        self.saved.pop(key_id, None)


class FakeJobSubmitter:
    """Реализация ``JobSubmitterPort``, фиксирующая поставленные в очередь id."""

    def __init__(self) -> None:
        self.submitted: list[str] = []

    async def submit(self, job_id: str) -> None:
        self.submitted.append(job_id)
