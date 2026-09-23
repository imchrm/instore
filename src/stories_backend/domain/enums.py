"""Перечисления домена: статусы задачи, режимы приведения под Stories и коды ошибок."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Статус задачи в автомате состояний."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCODING = "transcoding"
    SEGMENTING = "segmenting"
    PROBING = "probing"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


class StoriesFit(StrEnum):
    """Режим приведения кадра к вертикали 1080x1920 под Stories."""

    NONE = "none"
    COVER = "cover"
    PAD = "pad"


class ErrorCode(StrEnum):
    """Таксономия доменных ошибок, попадающая в ответ клиенту."""

    URL_UNSUPPORTED = "URL_UNSUPPORTED"
    VIDEO_UNAVAILABLE = "VIDEO_UNAVAILABLE"
    VIDEO_PRIVATE = "VIDEO_PRIVATE"
    GEO_BLOCKED = "GEO_BLOCKED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    TOO_LONG = "TOO_LONG"
    TOO_LARGE = "TOO_LARGE"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    TRANSCODE_FAILED = "TRANSCODE_FAILED"
    SEGMENT_FAILED = "SEGMENT_FAILED"
    INTERNAL = "INTERNAL"
