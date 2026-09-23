"""Маппинг доменных сущностей в DTO транспорта."""

from __future__ import annotations

from collections.abc import Callable

from stories_backend.application.config import ProcessingLimits
from stories_backend.domain.entities import CookiesStatus, Job, ProgressEvent
from stories_backend.domain.enums import StoriesFit
from stories_backend.interface.api.schemas import (
    ChunkInfo,
    CookiesStatusDto,
    ErrorInfo,
    JobResponse,
    ProgressEventDto,
    ServiceConfigDto,
)

# Построитель URL куска по (job_id, index) - роутер знает конкретный путь.
ChunkUrlBuilder = Callable[[str, int], str]


def job_to_response(job: Job, chunk_url: ChunkUrlBuilder) -> JobResponse:
    """Собрать ``JobResponse`` из доменной задачи."""
    error = None
    if job.error_code is not None:
        error = ErrorInfo(code=job.error_code, message=job.error_message or job.error_code.value)
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        source_title=job.meta.title if job.meta is not None else None,
        source_duration_sec=job.meta.duration_sec if job.meta is not None else None,
        progress=job.progress,
        chunks=[
            ChunkInfo(
                index=chunk.index,
                filename=chunk.filename,
                url=chunk_url(job.job_id, chunk.index),
                duration_sec=chunk.duration_sec,
                size_bytes=chunk.size_bytes,
                sha256=chunk.sha256,
                over_limit=chunk.over_limit,
            )
            for chunk in job.chunks
        ],
        error=error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def progress_event_to_dto(event: ProgressEvent) -> ProgressEventDto:
    """Собрать DTO события прогресса."""
    return ProgressEventDto(
        job_id=event.job_id,
        status=event.status,
        phase_progress=event.phase_progress,
        message=event.message,
    )


def cookies_status_to_dto(status: CookiesStatus) -> CookiesStatusDto:
    """Собрать DTO состояния cookies."""
    return CookiesStatusDto(
        present=status.present,
        uploaded_at=status.uploaded_at,
        likely_expired=status.likely_expired,
    )


def limits_to_service_config(limits: ProcessingLimits) -> ServiceConfigDto:
    """Собрать публикуемую конфигурацию сервиса из лимитов."""
    return ServiceConfigDto(
        max_filesize_mb=limits.max_filesize_mb,
        max_height_default=limits.max_height_default,
        segment_time_default=limits.segment_time_default,
        keyframe_limit_sec=limits.keyframe_limit_sec,
        stories_fit_options=list(StoriesFit),
        job_ttl_seconds=limits.job_ttl_seconds,
    )
