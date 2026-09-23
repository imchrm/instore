"""Доменные сущности, value objects и автомат переходов статусов задачи."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from .enums import ErrorCode, JobStatus, StoriesFit
from .errors import InvalidStatusTransitionError


@dataclass(slots=True, frozen=True)
class Chunk:
    """Один нарезанный сегмент готового видео."""

    index: int
    filename: str
    duration_sec: float
    size_bytes: int
    sha256: str
    over_limit: bool


@dataclass(slots=True, frozen=True)
class VideoMeta:
    """Метаданные исходного видео, полученные до/после скачивания."""

    title: str | None
    duration_sec: float | None
    filesize_bytes: int | None
    height: int | None


@dataclass(slots=True, frozen=True)
class ProgressEvent:
    """Событие прогресса обработки задачи (доменное представление)."""

    job_id: str
    status: JobStatus
    phase_progress: float
    message: str | None = None


@dataclass(slots=True, frozen=True)
class CookiesStatus:
    """Состояние cookies, привязанных к ``key_id``."""

    present: bool
    uploaded_at: float | None = None
    likely_expired: bool = False


_ALLOWED_TRANSITIONS: Final[dict[JobStatus, frozenset[JobStatus]]] = {
    JobStatus.QUEUED: frozenset({JobStatus.DOWNLOADING, JobStatus.FAILED}),
    JobStatus.DOWNLOADING: frozenset({JobStatus.TRANSCODING, JobStatus.FAILED}),
    JobStatus.TRANSCODING: frozenset({JobStatus.SEGMENTING, JobStatus.FAILED}),
    JobStatus.SEGMENTING: frozenset({JobStatus.PROBING, JobStatus.FAILED}),
    JobStatus.PROBING: frozenset({JobStatus.READY, JobStatus.FAILED}),
    JobStatus.READY: frozenset({JobStatus.EXPIRED}),
    JobStatus.FAILED: frozenset(),
    JobStatus.EXPIRED: frozenset(),
}


def can_transition(src: JobStatus, dst: JobStatus) -> bool:
    """Разрешён ли переход статуса задачи из ``src`` в ``dst``."""
    return dst in _ALLOWED_TRANSITIONS[src]


@dataclass(slots=True)
class Job:
    """Единица обработки одного URL от приёма до готовности или ошибки."""

    job_id: str
    key_id: str
    url: str
    segment_time: int
    max_height: int
    stories_fit: StoriesFit
    use_cookies: bool
    status: JobStatus
    progress: float = 0.0
    meta: VideoMeta | None = None
    chunks: list[Chunk] = field(default_factory=list)
    error_code: ErrorCode | None = None
    error_message: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0

    def can_transition_to(self, status: JobStatus) -> bool:
        """Разрешён ли переход задачи в ``status`` из текущего статуса."""
        return can_transition(self.status, status)

    def transition_to(self, status: JobStatus) -> None:
        """Перевести задачу в ``status`` или бросить исключение при недопустимом переходе."""
        if not can_transition(self.status, status):
            raise InvalidStatusTransitionError(self.status, status)
        self.status = status

    def mark_failed(self, code: ErrorCode, message: str) -> None:
        """Перевести задачу в ``FAILED`` с фиксацией кода и сообщения об ошибке."""
        self.transition_to(JobStatus.FAILED)
        self.error_code = code
        self.error_message = message
