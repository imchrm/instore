"""Сценарий удаления задачи и её файлов с изоляцией по ``key_id``."""

from __future__ import annotations

from stories_backend.domain.ports import JobRepositoryPort, StoragePort


class DeleteJobUseCase:
    """Удалить задачу (файлы + запись), если она принадлежит текущему ключу."""

    def __init__(self, repository: JobRepositoryPort, storage: StoragePort) -> None:
        self._repository = repository
        self._storage = storage

    async def execute(self, job_id: str, key_id: str) -> bool:
        job = await self._repository.get(job_id)
        if job is None or job.key_id != key_id:
            return False
        await self._storage.remove_job(job_id)
        await self._repository.delete(job_id)
        return True
