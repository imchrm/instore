"""Перекодирование через ``ffmpeg`` с приведением под Stories (реализация ``TranscoderPort``).

Кейфреймы форсируются на границах сегмента (``force_key_frames``), поэтому
последующая нарезка выполняется копированием потока. Прогресс читается из
``-progress pipe:1`` и переводится в долю от полной длительности исходника.
"""

from __future__ import annotations

from stories_backend.domain.enums import StoriesFit
from stories_backend.domain.errors import DomainError, TranscodeFailedError
from stories_backend.domain.ports import MediaProbePort, ProgressCallback
from stories_backend.infrastructure.process.runner import ProcessRunner

_STDERR_TAIL = 400

# Фильтры приведения кадра к вертикали 1080x1920.
_COVER_VF = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
_PAD_FILTER_COMPLEX = (
    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
    "crop=1080:1920,boxblur=20[bg];"
    "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
    "[bg][fg]overlay=(W-w)/2:(H-h)/2"
)


class _ProgressEmitter:
    """Парсер строк ``-progress`` ffmpeg, переводящий ``out_time_us`` в долю фазы."""

    def __init__(self, total_sec: float, on_progress: ProgressCallback) -> None:
        self._total_sec = total_sec
        self._on_progress = on_progress

    async def feed(self, line: str) -> None:
        key, separator, value = line.partition("=")
        if not separator or key != "out_time_us" or self._total_sec <= 0:
            return
        try:
            micros = float(value)
        except ValueError:
            return
        fraction = max(0.0, min(micros / 1_000_000.0 / self._total_sec, 1.0))
        await self._on_progress(fraction, None)


class FfmpegTranscoder:
    """Перекодирование исходника в совместимый с Telegram формат."""

    def __init__(
        self,
        runner: ProcessRunner,
        probe: MediaProbePort,
        *,
        ffmpeg_bin: str = "ffmpeg",
    ) -> None:
        self._runner = runner
        self._probe = probe
        self._ffmpeg_bin = ffmpeg_bin

    async def transcode(
        self,
        src: str,
        dest: str,
        *,
        segment_time: int,
        fps: int,
        stories_fit: StoriesFit,
        on_progress: ProgressCallback,
    ) -> None:
        total_sec = await self._safe_duration(src)
        argv = self._build_argv(
            src, dest, segment_time=segment_time, fps=fps, stories_fit=stories_fit
        )
        emitter = _ProgressEmitter(total_sec, on_progress)
        result = await self._runner.run_streaming(argv, emitter.feed)
        if result.returncode != 0:
            tail = result.stderr.strip()[-_STDERR_TAIL:]
            msg = f"ffmpeg (transcode) завершился с кодом {result.returncode}: {tail}"
            raise TranscodeFailedError(msg)
        await on_progress(1.0, None)

    async def _safe_duration(self, src: str) -> float:
        """Длительность исходника для расчёта прогресса; при ошибке - 0 (прогресс без долей)."""
        try:
            return await self._probe.duration_sec(src)
        except DomainError:
            return 0.0

    def _build_argv(
        self,
        src: str,
        dest: str,
        *,
        segment_time: int,
        fps: int,
        stories_fit: StoriesFit,
    ) -> list[str]:
        argv = [
            self._ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-i",
            src,
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
        ]
        argv.extend(_fit_filter_args(stories_fit))
        argv.extend(
            [
                "-force_key_frames",
                f"expr:gte(t,n_forced*{segment_time})",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                "-progress",
                "pipe:1",
                "-nostats",
                dest,
            ]
        )
        return argv


def _fit_filter_args(stories_fit: StoriesFit) -> list[str]:
    if stories_fit is StoriesFit.NONE:
        return []
    if stories_fit is StoriesFit.COVER:
        return ["-vf", _COVER_VF]
    return ["-filter_complex", _PAD_FILTER_COMPLEX]
