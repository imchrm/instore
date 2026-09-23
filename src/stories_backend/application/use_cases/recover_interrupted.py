"""Сценарий восстановления после рестарта: пометить прерванные задачи как FAILED."""

from __future__ import annotations

import time

from stories_backend.application.ports import Clock
from stories_backend.domain.entities import ProgressEvent
from stories_backend.domain.enums import ErrorCode, JobStatus
from stories_backend.domain.ports import EventBusPort, JobRepositoryPort

_MESSAGE = "обработка прервана рестартом сервиса"


class RecoverInterruptedUseCase:
    """Найти незавершённые задачи и перевести их в ``FAILED`` (``INTERNAL``)."""

    def __init__(
        self,
        repository: JobRepositoryPort,
        event_bus: EventBusPort,
        *,
        clock: Clock = time.time,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._clock = clock

    async def execute(self) -> list[str]:
        jobs = await self._repository.list_unfinished()
        recovered: list[str] = []
        for job in jobs:
            job.mark_failed(ErrorCode.INTERNAL, _MESSAGE)
            job.updated_at = self._clock()
            await self._repository.update(job)
            await self._event_bus.publish(
                job.job_id,
                ProgressEvent(
                    job_id=job.job_id,
                    status=JobStatus.FAILED,
                    phase_progress=job.progress,
                    message=_MESSAGE,
                ),
            )
            recovered.append(job.job_id)
        return recovered
