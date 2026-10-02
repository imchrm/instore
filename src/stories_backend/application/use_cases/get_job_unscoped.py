"""Чтение задачи по ``job_id`` без изоляции по ключу.

Нужно публичному эндпоинту отдачи куска по подписанной ссылке: авторизацией там
служит подпись URL, а не ``X-API-Key``, поэтому ``key_id`` недоступен. Для всех
маршрутов, доступных по ключу, по-прежнему используется ``GetJobUseCase``.
"""

from __future__ import annotations

from stories_backend.domain.entities import Job
from stories_backend.domain.ports import JobRepositoryPort


class GetJobUnscopedUseCase:
    """Вернуть задачу по идентификатору без проверки принадлежности ключу."""

    def __init__(self, repository: JobRepositoryPort) -> None:
        self._repository = repository

    async def execute(self, job_id: str) -> Job | None:
        return await self._repository.get(job_id)
