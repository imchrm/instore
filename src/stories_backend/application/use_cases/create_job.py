"""Сценарий создания задачи: регистрация и постановка в очередь."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from stories_backend.application.ports import Clock, IdGenerator, JobSubmitterPort
from stories_backend.domain.entities import Job
from stories_backend.domain.enums import JobStatus, StoriesFit
from stories_backend.domain.ports import JobRepositoryPort


@dataclass(frozen=True, slots=True)
class CreateJobCommand:
    """Входные данные создания задачи (доменное представление запроса)."""

    key_id: str
    url: str
    segment_time: int
    max_height: int
    stories_fit: StoriesFit
    use_cookies: bool


def _default_id() -> str:
    return uuid.uuid4().hex


class CreateJobUseCase:
    """Создать задачу в статусе ``QUEUED`` и поставить её в очередь обработки."""

    def __init__(
        self,
        repository: JobRepositoryPort,
        submitter: JobSubmitterPort,
        *,
        clock: Clock = time.time,
        id_generator: IdGenerator = _default_id,
    ) -> None:
        self._repository = repository
        self._submitter = submitter
        self._clock = clock
        self._id_generator = id_generator

    async def execute(self, command: CreateJobCommand) -> Job:
        now = self._clock()
        job = Job(
            job_id=self._id_generator(),
            key_id=command.key_id,
            url=command.url,
            segment_time=command.segment_time,
            max_height=command.max_height,
            stories_fit=command.stories_fit,
            use_cookies=command.use_cookies,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        await self._repository.add(job)
        await self._submitter.submit(job.job_id)
        return job
