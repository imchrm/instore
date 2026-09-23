"""Сценарий подписки на поток прогресса задачи (SSE) с изоляцией по ``key_id``."""

from __future__ import annotations

from collections.abc import AsyncIterator

from stories_backend.domain.entities import ProgressEvent
from stories_backend.domain.ports import EventBusPort, JobRepositoryPort


class StreamProgressUseCase:
    """Вернуть поток событий прогресса задачи, если она принадлежит ключу."""

    def __init__(self, repository: JobRepositoryPort, event_bus: EventBusPort) -> None:
        self._repository = repository
        self._event_bus = event_bus

    async def execute(self, job_id: str, key_id: str) -> AsyncIterator[ProgressEvent] | None:
        job = await self._repository.get(job_id)
        if job is None or job.key_id != key_id:
            return None
        return self._event_bus.subscribe(job_id)
