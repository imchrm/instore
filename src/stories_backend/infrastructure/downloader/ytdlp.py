"""Скачивание исходного видео через ``yt-dlp`` (реализация ``VideoDownloaderPort``).

Метаданные снимаются командой ``yt-dlp -J`` (dump JSON), скачивание идёт с
жёстким ограничением размера (``--max-filesize``) и высоты. Прогресс читается из
строк ``[download] ... %`` (режим ``--newline``). Ошибки yt-dlp эвристически
отображаются в доменную таксономию :class:`ErrorCode`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from stories_backend.domain.entities import VideoMeta
from stories_backend.domain.errors import (
    AuthRequiredError,
    DomainError,
    DownloadFailedError,
    GeoBlockedError,
    TooLargeError,
    VideoPrivateError,
    VideoUnavailableError,
)
from stories_backend.domain.ports import ProgressCallback
from stories_backend.infrastructure.process.runner import ProcessRunner

_STDERR_TAIL = 400
_SOURCE_STEM = "source"
_PROGRESS_RE = re.compile(r"\[download\]\s+([\d.]+)%")

# Эвристики отображения текста ошибки yt-dlp в доменные исключения. Порядок важен:
# более специфичные подстроки идут раньше общих.
_ERROR_PATTERNS: tuple[tuple[str, type[DomainError]], ...] = (
    ("is private", VideoPrivateError),
    ("private video", VideoPrivateError),
    ("sign in", AuthRequiredError),
    ("log in", AuthRequiredError),
    ("login required", AuthRequiredError),
    ("cookies", AuthRequiredError),
    ("authentication", AuthRequiredError),
    ("not available in your country", GeoBlockedError),
    ("geo", GeoBlockedError),
    ("blocked", GeoBlockedError),
    ("larger than", TooLargeError),
    ("max-filesize", TooLargeError),
    ("video unavailable", VideoUnavailableError),
    ("not available", VideoUnavailableError),
    ("unavailable", VideoUnavailableError),
)


def _map_error(stderr: str) -> DomainError:
    lowered = stderr.lower()
    for needle, error_type in _ERROR_PATTERNS:
        if needle in lowered:
            return error_type(stderr.strip()[-_STDERR_TAIL:])
    return DownloadFailedError(stderr.strip()[-_STDERR_TAIL:])


class YtDlpDownloader:
    """Адаптер скачивания и снятия метаданных на базе ``yt-dlp``."""

    def __init__(self, runner: ProcessRunner, *, ytdlp_bin: str = "yt-dlp") -> None:
        self._runner = runner
        self._ytdlp_bin = ytdlp_bin

    async def probe_meta(self, url: str, *, cookies_path: str | None) -> VideoMeta:
        argv = [self._ytdlp_bin, "-J", "--no-warnings", "--no-playlist"]
        argv.extend(_cookies_args(cookies_path))
        argv.append(url)
        result = await self._runner.run(argv)
        if result.returncode != 0:
            raise _map_error(result.stderr)
        try:
            data: dict[str, Any] = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            msg = "yt-dlp вернул неразбираемый JSON метаданных"
            raise DownloadFailedError(msg) from exc
        return _meta_from_info(data)

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
        output_template = str(Path(dest_dir) / f"{_SOURCE_STEM}.%(ext)s")
        argv = [
            self._ytdlp_bin,
            "--no-warnings",
            "--no-playlist",
            "--newline",
            "-f",
            f"bv*[height<={max_height}]+ba/b[height<={max_height}]",
            "--max-filesize",
            f"{max_filesize_mb}M",
            "-o",
            output_template,
        ]
        argv.extend(_cookies_args(cookies_path))
        argv.append(url)

        emitter = _ProgressEmitter(on_progress)
        result = await self._runner.run_streaming(argv, emitter.feed)
        if result.returncode != 0:
            raise _map_error(result.stderr)
        source_path = _find_source(dest_dir)
        if source_path is None:
            msg = "yt-dlp завершился успешно, но файл-исходник не найден"
            raise DownloadFailedError(msg)
        await on_progress(1.0, None)
        return source_path


class _ProgressEmitter:
    """Извлечение процента загрузки из строк ``[download] ... %``."""

    def __init__(self, on_progress: ProgressCallback) -> None:
        self._on_progress = on_progress

    async def feed(self, line: str) -> None:
        match = _PROGRESS_RE.search(line)
        if match is None:
            return
        try:
            percent = float(match.group(1))
        except ValueError:
            return
        await self._on_progress(max(0.0, min(percent / 100.0, 1.0)), None)


def _cookies_args(cookies_path: str | None) -> list[str]:
    return [] if cookies_path is None else ["--cookies", cookies_path]


def _meta_from_info(info: dict[str, Any]) -> VideoMeta:
    filesize = info.get("filesize")
    if filesize is None:
        filesize = info.get("filesize_approx")
    return VideoMeta(
        title=info.get("title"),
        duration_sec=info.get("duration"),
        filesize_bytes=filesize,
        height=info.get("height"),
    )


def _find_source(dest_dir: str) -> str | None:
    candidates = sorted(
        path for path in Path(dest_dir).glob(f"{_SOURCE_STEM}.*") if path.suffix != ".part"
    )
    return str(candidates[0]) if candidates else None
