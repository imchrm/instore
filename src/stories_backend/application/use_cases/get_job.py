"""Сценарий чтения задачи с изоляцией по ``key_id``."""

from __future__ import annotations

from stories_backend.domain.entities import Job
from stories_backend.domain.ports import JobRepositoryPort


class GetJobUseCase:
    """Вернуть задачу, если она принадлежит текущему ключу."""

    def __init__(self, repository: JobRepositoryPort) -> None:
        self._repository = repository

    async def execute(self, job_id: str, key_id: str) -> Job | None:
        job = await self._repository.get(job_id)
        # Чужая (или отсутствующая) задача неотличима от несуществующей.
        if job is None or job.key_id != key_id:
            return None
        return job
