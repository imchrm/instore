"""Порты домена (Protocol): контракты внешних возможностей без их реализации.

Осознанно отсутствует порт публикации в Telegram Stories: авто-постинг вне
области проекта.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

from .entities import CookiesStatus, Job, ProgressEvent, VideoMeta
from .enums import StoriesFit

# Доля прогресса текущей фазы (0..1) и опциональное сообщение.
ProgressCallback = Callable[[float, str | None], Awaitable[None]]


class VideoDownloaderPort(Protocol):
    """Скачивание исходного видео и снятие его метаданных."""

    async def probe_meta(self, url: str, *, cookies_path: str | None) -> VideoMeta: ...

    async def download(
        self,
        url: str,
        dest_dir: str,
        *,
        max_height: int,
        max_filesize_mb: int,
        cookies_path: str | None,
        on_progress: ProgressCallback,
    ) -> str:
        """Скачать видео и вернуть путь к файлу-исходнику."""
        ...


class TranscoderPort(Protocol):
    """Перекодирование с принудительными кейфреймами и приведением под Stories."""

    async def transcode(
        self,
        src: str,
        dest: str,
        *,
        segment_time: int,
        fps: int,
        stories_fit: StoriesFit,
        on_progress: ProgressCallback,
    ) -> None: ...


class SegmenterPort(Protocol):
    """Нарезка перекодированного видео на сегменты копированием потока."""

    async def segment(self, src: str, out_pattern: str, *, segment_time: int) -> list[str]: ...


class MediaProbePort(Protocol):
    """Измерение параметров медиафайла."""

    async def duration_sec(self, path: str) -> float: ...


class JobRepositoryPort(Protocol):
    """Персистентность задач между рестартами."""

    async def add(self, job: Job) -> None: ...

    async def get(self, job_id: str) -> Job | None: ...

    async def update(self, job: Job) -> None: ...

    async def delete(self, job_id: str) -> None: ...

    async def list_expired(self, ttl_seconds: int) -> list[Job]: ...

    async def list_unfinished(self) -> list[Job]:
        """Задачи в незавершённых статусах (не ready/failed/expired) для восстановления."""
        ...


class EventBusPort(Protocol):
    """Шина событий прогресса обработки (публикация/подписка в пределах процесса)."""

    async def publish(self, job_id: str, event: ProgressEvent) -> None: ...

    def subscribe(self, job_id: str) -> AsyncIterator[ProgressEvent]: ...


class StoragePort(Protocol):
    """Файловое хранилище задач и кусков."""

    def job_dir(self, job_id: str) -> str: ...

    async def remove_job(self, job_id: str) -> None: ...

    async def remove_intermediate(self, job_id: str) -> None: ...


class CookiesStorePort(Protocol):
    """Хранение cookies по ``key_id``."""

    async def save(self, key_id: str, content: bytes) -> None: ...

    async def path(self, key_id: str) -> str | None: ...

    async def status(self, key_id: str) -> CookiesStatus: ...

    async def delete(self, key_id: str) -> None: ...
