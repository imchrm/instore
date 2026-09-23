"""Измерение длительности медиафайла через ``ffprobe`` (реализация ``MediaProbePort``)."""

from __future__ import annotations

from stories_backend.domain.errors import InternalError
from stories_backend.infrastructure.process.runner import ProcessRunner

_STDERR_TAIL = 200


class FfprobeMediaProbe:
    """Определение длительности файла через ``ffprobe``."""

    def __init__(self, runner: ProcessRunner, *, ffprobe_bin: str = "ffprobe") -> None:
        self._runner = runner
        self._ffprobe_bin = ffprobe_bin

    async def duration_sec(self, path: str) -> float:
        argv = [
            self._ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        result = await self._runner.run(argv)
        if result.returncode != 0:
            tail = result.stderr.strip()[-_STDERR_TAIL:]
            msg = f"ffprobe завершился с кодом {result.returncode}: {tail}"
            raise InternalError(msg)
        text = result.stdout.strip()
        try:
            return float(text)
        except ValueError as exc:
            msg = f"ffprobe вернул неразбираемую длительность: {text!r}"
            raise InternalError(msg) from exc
