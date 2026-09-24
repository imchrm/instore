"""Нарезка видео на сегменты копированием потока через ``ffmpeg`` (``SegmenterPort``)."""

from __future__ import annotations

import re
from pathlib import Path

from stories_backend.domain.errors import SegmentFailedError
from stories_backend.infrastructure.process.runner import ProcessRunner

_STDERR_TAIL = 400
_PRINTF_TOKEN = re.compile(r"%\d*d")

# Допуск выбора точки нарезки. Кейфреймы форсируются ровно на границах сегмента
# (t = n*segment_time), но муксер segment режет на первом кейфрейме строго
# ПОЗЖЕ границы, из-за чего кейфрейм точно на границе пропускается и сегмент
# получается двойной длины. Небольшой delta включает пограничный кейфрейм в
# окно нарезки и гарантирует куски не длиннее segment_time.
_SEGMENT_TIME_DELTA = "0.1"


def _pattern_to_glob(name: str) -> str:
    """Преобразовать printf-шаблон имени (``conv_%03d.mp4``) в glob (``conv_*.mp4``)."""
    return _PRINTF_TOKEN.sub("*", name)


class FfmpegSegmenter:
    """Нарезка перекодированного видео на сегменты без повторного кодирования."""

    def __init__(self, runner: ProcessRunner, *, ffmpeg_bin: str = "ffmpeg") -> None:
        self._runner = runner
        self._ffmpeg_bin = ffmpeg_bin

    async def segment(self, src: str, out_pattern: str, *, segment_time: int) -> list[str]:
        argv = [
            self._ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-i",
            src,
            "-c",
            "copy",
            "-map",
            "0",
            "-segment_time",
            str(segment_time),
            "-segment_time_delta",
            _SEGMENT_TIME_DELTA,
            "-f",
            "segment",
            "-reset_timestamps",
            "1",
            out_pattern,
        ]
        result = await self._runner.run(argv)
        if result.returncode != 0:
            tail = result.stderr.strip()[-_STDERR_TAIL:]
            msg = f"ffmpeg (segment) завершился с кодом {result.returncode}: {tail}"
            raise SegmentFailedError(msg)
        return self._list_segments(out_pattern)

    @staticmethod
    def _list_segments(out_pattern: str) -> list[str]:
        pattern_path = Path(out_pattern)
        glob_name = _pattern_to_glob(pattern_path.name)
        return sorted(str(path) for path in pattern_path.parent.glob(glob_name))
