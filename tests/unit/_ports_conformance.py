"""Статическая проверка соответствия адаптеров портам домена.

Модуль не содержит тестов и не исполняется в рантайме: он существует только
для ``mypy`` (проверка выполняется в блоке ``TYPE_CHECKING``). Имя с префиксом
``_`` исключает его из сбора pytest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import cast

    import aiosqlite

    from stories_backend.domain.ports import (
        CookiesStorePort,
        EventBusPort,
        JobRepositoryPort,
        MediaProbePort,
        SegmenterPort,
        StoragePort,
        TranscoderPort,
        VideoDownloaderPort,
    )
    from stories_backend.infrastructure.cookies.filesystem_cookies import FilesystemCookiesStore
    from stories_backend.infrastructure.downloader.ytdlp import YtDlpDownloader
    from stories_backend.infrastructure.events.sse_bus import InProcessEventBus
    from stories_backend.infrastructure.media.ffmpeg_segmenter import FfmpegSegmenter
    from stories_backend.infrastructure.media.ffmpeg_transcoder import FfmpegTranscoder
    from stories_backend.infrastructure.media.ffprobe_probe import FfprobeMediaProbe
    from stories_backend.infrastructure.persistence.sqlite_repo import SqliteJobRepository
    from stories_backend.infrastructure.process.runner import AsyncioProcessRunner
    from stories_backend.infrastructure.storage.filesystem_storage import FilesystemStorage

    _runner = AsyncioProcessRunner()
    _probe: MediaProbePort = FfprobeMediaProbe(_runner)

    _storage: StoragePort = FilesystemStorage("/tmp/data")
    _cookies: CookiesStorePort = FilesystemCookiesStore("/tmp/cookies")
    _bus: EventBusPort = InProcessEventBus()
    _repo: JobRepositoryPort = SqliteJobRepository(cast("aiosqlite.Connection", None))
    _segmenter: SegmenterPort = FfmpegSegmenter(_runner)
    _transcoder: TranscoderPort = FfmpegTranscoder(_runner, _probe)
    _downloader: VideoDownloaderPort = YtDlpDownloader(_runner)
