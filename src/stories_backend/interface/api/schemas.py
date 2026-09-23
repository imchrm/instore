"""DTO транспорта (Pydantic v2): запросы и ответы HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl

from stories_backend.domain.enums import ErrorCode, JobStatus, StoriesFit


class JobCreateRequest(BaseModel):
    """Запрос на создание задачи."""

    url: HttpUrl
    segment_time: int = Field(default=45, ge=5, le=60)
    max_height: int = Field(default=1080, ge=240, le=2160)
    stories_fit: StoriesFit = StoriesFit.NONE
    use_cookies: bool = False


class ChunkInfo(BaseModel):
    """Описание одного куска в ответе."""

    index: int
    filename: str
    url: str
    duration_sec: float
    size_bytes: int
    sha256: str
    over_limit: bool


class ErrorInfo(BaseModel):
    """Информация об ошибке задачи."""

    code: ErrorCode
    message: str


class JobResponse(BaseModel):
    """Ответ со статусом/манифестом задачи."""

    job_id: str
    status: JobStatus
    source_title: str | None = None
    source_duration_sec: float | None = None
    progress: float = 0.0
    chunks: list[ChunkInfo] = Field(default_factory=list)
    error: ErrorInfo | None = None
    created_at: float
    updated_at: float


class ProgressEventDto(BaseModel):
    """Событие прогресса обработки (SSE)."""

    job_id: str
    status: JobStatus
    phase_progress: float
    message: str | None = None


class CookiesStatusDto(BaseModel):
    """Состояние cookies текущего ключа."""

    present: bool
    uploaded_at: float | None = None
    likely_expired: bool = False


class ServiceConfigDto(BaseModel):
    """Публикуемые лимиты и дефолты сервиса."""

    max_filesize_mb: int
    max_height_default: int
    segment_time_default: int
    keyframe_limit_sec: int
    stories_fit_options: list[StoriesFit]
    job_ttl_seconds: int
