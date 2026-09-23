"""Доменные исключения, привязанные к таксономии :class:`ErrorCode`."""

from __future__ import annotations

from typing import ClassVar, Final

from .enums import ErrorCode, JobStatus


class DomainError(Exception):
    """Базовая доменная ошибка.

    Каждый подкласс фиксирует свой :class:`ErrorCode` в атрибуте ``code``.
    Сообщение по умолчанию берётся из значения кода, если не задано явно.
    """

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL

    def __init__(self, message: str | None = None) -> None:
        self.message: str = message if message is not None else self.code.value
        super().__init__(self.message)


class UrlUnsupportedError(DomainError):
    """URL не поддерживается (не YouTube/Instagram или неверный формат)."""

    code = ErrorCode.URL_UNSUPPORTED


class VideoUnavailableError(DomainError):
    """Видео недоступно у источника."""

    code = ErrorCode.VIDEO_UNAVAILABLE


class VideoPrivateError(DomainError):
    """Видео приватное и требует прав, которых нет."""

    code = ErrorCode.VIDEO_PRIVATE


class GeoBlockedError(DomainError):
    """Видео заблокировано по региону."""

    code = ErrorCode.GEO_BLOCKED


class AuthRequiredError(DomainError):
    """Требуются cookies/авторизация (типично для Instagram)."""

    code = ErrorCode.AUTH_REQUIRED


class TooLongError(DomainError):
    """Длительность исходника превышает допустимый предел."""

    code = ErrorCode.TOO_LONG


class TooLargeError(DomainError):
    """Размер исходника превышает ``MAX_FILESIZE_MB``."""

    code = ErrorCode.TOO_LARGE


class DownloadFailedError(DomainError):
    """Сбой на этапе скачивания."""

    code = ErrorCode.DOWNLOAD_FAILED


class TranscodeFailedError(DomainError):
    """Сбой на этапе перекодирования."""

    code = ErrorCode.TRANSCODE_FAILED


class SegmentFailedError(DomainError):
    """Сбой на этапе нарезки."""

    code = ErrorCode.SEGMENT_FAILED


class InternalError(DomainError):
    """Внутренняя ошибка обработки."""

    code = ErrorCode.INTERNAL


class InvalidStatusTransitionError(DomainError):
    """Недопустимый переход в автомате состояний задачи.

    Это ошибка программиста, поэтому относится к коду ``INTERNAL``.
    """

    code = ErrorCode.INTERNAL

    def __init__(self, src: JobStatus, dst: JobStatus) -> None:
        self.src: JobStatus = src
        self.dst: JobStatus = dst
        super().__init__(f"Недопустимый переход статуса: {src.value} -> {dst.value}")


_ERROR_BY_CODE: Final[dict[ErrorCode, type[DomainError]]] = {
    ErrorCode.URL_UNSUPPORTED: UrlUnsupportedError,
    ErrorCode.VIDEO_UNAVAILABLE: VideoUnavailableError,
    ErrorCode.VIDEO_PRIVATE: VideoPrivateError,
    ErrorCode.GEO_BLOCKED: GeoBlockedError,
    ErrorCode.AUTH_REQUIRED: AuthRequiredError,
    ErrorCode.TOO_LONG: TooLongError,
    ErrorCode.TOO_LARGE: TooLargeError,
    ErrorCode.DOWNLOAD_FAILED: DownloadFailedError,
    ErrorCode.TRANSCODE_FAILED: TranscodeFailedError,
    ErrorCode.SEGMENT_FAILED: SegmentFailedError,
    ErrorCode.INTERNAL: InternalError,
}


def error_for_code(code: ErrorCode) -> type[DomainError]:
    """Вернуть класс исключения, соответствующий коду ошибки."""
    return _ERROR_BY_CODE[code]
