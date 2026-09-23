"""DI-контейнер: собранные сценарии и зависимости, доступные роутерам.

Наполняется в ``lifespan`` приложения и кладётся в ``app.state.container``.
"""

from __future__ import annotations

from dataclasses import dataclass

from stories_backend.application.config import ProcessingLimits
from stories_backend.application.use_cases.cookies_admin import CookiesAdminUseCase
from stories_backend.application.use_cases.create_job import CreateJobUseCase
from stories_backend.application.use_cases.delete_job import DeleteJobUseCase
from stories_backend.application.use_cases.get_job import GetJobUseCase
from stories_backend.application.use_cases.stream_progress import StreamProgressUseCase
from stories_backend.domain.ports import StoragePort
from stories_backend.infrastructure.security.api_keys import ApiKeyRegistry
from stories_backend.interface.config import Settings


@dataclass(frozen=True, slots=True)
class Container:
    """Собранные компоненты приложения, нужные слою HTTP."""

    settings: Settings
    limits: ProcessingLimits
    api_keys: ApiKeyRegistry
    storage: StoragePort
    create_job: CreateJobUseCase
    get_job: GetJobUseCase
    delete_job: DeleteJobUseCase
    stream_progress: StreamProgressUseCase
    cookies_admin: CookiesAdminUseCase
