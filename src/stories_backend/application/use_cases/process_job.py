"""Сценарий обработки задачи воркером: загрузка задачи и запуск конвейера."""

from __future__ import annotations

from stories_backend.application.services.job_processing import JobProcessingService
from stories_backend.domain.ports import JobRepositoryPort


class ProcessJobUseCase:
    """Загрузить задачу по id и прогнать её через конвейер обработки."""

    def __init__(self, repository: JobRepositoryPort, service: JobProcessingService) -> None:
        self._repository = repository
        self._service = service

    async def execute(self, job_id: str) -> None:
        job = await self._repository.get(job_id)
        if job is None:
            return
        await self._service.process(job)
