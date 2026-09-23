"""Сборка FastAPI-приложения: DI-граф, жизненный цикл, роутеры.

``lifespan`` при старте открывает БД, собирает адаптеры и сценарии, восстанавливает
прерванные задачи и запускает воркер и планировщик; при остановке аккуратно
гасит их и закрывает БД. Используйте фабрику ``create_app`` (в т.ч. как
``uvicorn --factory``).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from stories_backend.application.services.job_processing import JobProcessingService
from stories_backend.application.use_cases.cleanup_expired import CleanupExpiredUseCase
from stories_backend.application.use_cases.cookies_admin import CookiesAdminUseCase
from stories_backend.application.use_cases.create_job import CreateJobUseCase
from stories_backend.application.use_cases.delete_job import DeleteJobUseCase
from stories_backend.application.use_cases.get_job import GetJobUseCase
from stories_backend.application.use_cases.process_job import ProcessJobUseCase
from stories_backend.application.use_cases.recover_interrupted import RecoverInterruptedUseCase
from stories_backend.application.use_cases.stream_progress import StreamProgressUseCase
from stories_backend.infrastructure.cookies.filesystem_cookies import FilesystemCookiesStore
from stories_backend.infrastructure.downloader.ytdlp import YtDlpDownloader
from stories_backend.infrastructure.events.sse_bus import InProcessEventBus
from stories_backend.infrastructure.media.ffmpeg_segmenter import FfmpegSegmenter
from stories_backend.infrastructure.media.ffmpeg_transcoder import FfmpegTranscoder
from stories_backend.infrastructure.media.ffprobe_probe import FfprobeMediaProbe
from stories_backend.infrastructure.persistence.sqlite_repo import SqliteJobRepository
from stories_backend.infrastructure.process.runner import AsyncioProcessRunner
from stories_backend.infrastructure.security.api_keys import ApiKeyRegistry
from stories_backend.infrastructure.storage.filesystem_storage import FilesystemStorage
from stories_backend.interface.api.container import Container
from stories_backend.interface.api.routers import admin, jobs, system
from stories_backend.interface.config import Settings
from stories_backend.worker.queue import JobQueue
from stories_backend.worker.scheduler import PeriodicCleanupScheduler


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    limits = settings.to_limits()

    repository = await SqliteJobRepository.connect(settings.db_path)
    storage = FilesystemStorage(settings.data_dir)
    cookies_store = FilesystemCookiesStore(settings.resolved_cookies_dir)
    event_bus = InProcessEventBus()

    runner = AsyncioProcessRunner()
    probe = FfprobeMediaProbe(runner)
    downloader = YtDlpDownloader(runner)
    transcoder = FfmpegTranscoder(runner, probe)
    segmenter = FfmpegSegmenter(runner)

    processing = JobProcessingService(
        repository=repository,
        storage=storage,
        event_bus=event_bus,
        downloader=downloader,
        transcoder=transcoder,
        segmenter=segmenter,
        probe=probe,
        cookies_store=cookies_store,
        limits=limits,
    )
    process_job = ProcessJobUseCase(repository, processing)
    queue = JobQueue(process_job, max_concurrent_jobs=settings.max_concurrent_jobs)
    cleanup = CleanupExpiredUseCase(repository, storage, event_bus, limits)
    scheduler = PeriodicCleanupScheduler(cleanup, interval_sec=limits.cleanup_interval_sec)
    recover = RecoverInterruptedUseCase(repository, event_bus)

    app.state.container = Container(
        settings=settings,
        limits=limits,
        api_keys=ApiKeyRegistry.from_config(settings.api_keys),
        storage=storage,
        create_job=CreateJobUseCase(repository, queue),
        get_job=GetJobUseCase(repository),
        delete_job=DeleteJobUseCase(repository, storage),
        stream_progress=StreamProgressUseCase(repository, event_bus),
        cookies_admin=CookiesAdminUseCase(cookies_store),
    )

    await recover.execute()
    await queue.start()
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        await queue.stop()
        await repository.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Создать приложение. Без аргумента настройки читаются из окружения."""
    app = FastAPI(title="stories-backend", lifespan=_lifespan)
    # Settings() без аргументов читает поля (в т.ч. api_keys) из окружения.
    resolved = settings if settings is not None else Settings()  # type: ignore[call-arg]
    app.state.settings = resolved
    app.include_router(system.router)
    app.include_router(jobs.router)
    app.include_router(admin.router)
    return app
