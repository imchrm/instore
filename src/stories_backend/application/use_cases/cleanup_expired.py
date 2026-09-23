"""Сценарий очистки: перевод готовых задач в ``EXPIRED`` по TTL и удаление файлов."""

from __future__ import annotations

import time

from stories_backend.application.config import ProcessingLimits
from stories_backend.application.ports import Clock
from stories_backend.domain.entities import ProgressEvent
from stories_backend.domain.enums import JobStatus
from stories_backend.domain.ports import EventBusPort, JobRepositoryPort, StoragePort


class CleanupExpiredUseCase:
    """Найти просроченные готовые задачи, удалить их файлы и пометить ``EXPIRED``."""

    def __init__(
        self,
        repository: JobRepositoryPort,
        storage: StoragePort,
        event_bus: EventBusPort,
        limits: ProcessingLimits,
        *,
        clock: Clock = time.time,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._event_bus = event_bus
        self._limits = limits
        self._clock = clock

    async def execute(self) -> list[str]:
        expired = await self._repository.list_expired(self._limits.job_ttl_seconds)
        cleaned: list[str] = []
        for job in expired:
            job.transition_to(JobStatus.EXPIRED)
            job.updated_at = self._clock()
            await self._storage.remove_job(job.job_id)
            await self._repository.update(job)
            await self._event_bus.publish(
                job.job_id,
                ProgressEvent(job_id=job.job_id, status=JobStatus.EXPIRED, phase_progress=1.0),
            )
            cleaned.append(job.job_id)
        return cleaned
