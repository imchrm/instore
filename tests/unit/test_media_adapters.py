"""Тесты медиа-адаптеров (ffprobe/ffmpeg) на фейковом раннере процессов."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from stories_backend.domain.enums import StoriesFit
from stories_backend.domain.errors import InternalError, SegmentFailedError, TranscodeFailedError
from stories_backend.infrastructure.media.ffmpeg_segmenter import FfmpegSegmenter
from stories_backend.infrastructure.media.ffmpeg_transcoder import FfmpegTranscoder
from stories_backend.infrastructure.media.ffprobe_probe import FfprobeMediaProbe
from stories_backend.infrastructure.process.runner import LineCallback, ProcessResult


class FakeProcessRunner:
    """Раннер с заранее заданным результатом; запоминает argv вызовов."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        stdout_lines: Sequence[str] = (),
    ) -> None:
        self._returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._stdout_lines = list(stdout_lines)
        self.calls: list[list[str]] = []

    async def run(self, argv: Sequence[str]) -> ProcessResult:
        self.calls.append(list(argv))
        return ProcessResult(self._returncode, self._stdout, self._stderr)

    async def run_streaming(
        self, argv: Sequence[str], on_stdout_line: LineCallback
    ) -> ProcessResult:
        self.calls.append(list(argv))
        for line in self._stdout_lines:
            await on_stdout_line(line)
        return ProcessResult(self._returncode, "", self._stderr)


class FakeProbe:
    """Заглушка ``MediaProbePort`` с фиксированной или падающей длительностью."""

    def __init__(self, duration: float, *, error: Exception | None = None) -> None:
        self._duration = duration
        self._error = error

    async def duration_sec(self, path: str) -> float:
        if self._error is not None:
            raise self._error
        return self._duration


class ProgressCollector:
    def __init__(self) -> None:
        self.events: list[tuple[float, str | None]] = []

    async def __call__(self, fraction: float, message: str | None) -> None:
        self.events.append((fraction, message))


# --- ffprobe ---------------------------------------------------------------


async def test_ffprobe_returns_duration() -> None:
    runner = FakeProcessRunner(stdout="12.5\n")
    probe = FfprobeMediaProbe(runner)

    assert await probe.duration_sec("/video.mp4") == 12.5
    assert runner.calls[0][0] == "ffprobe"
    assert "/video.mp4" in runner.calls[0]


async def test_ffprobe_nonzero_raises() -> None:
    probe = FfprobeMediaProbe(FakeProcessRunner(returncode=1, stderr="boom"))

    with pytest.raises(InternalError):
        await probe.duration_sec("/video.mp4")


async def test_ffprobe_unparsable_raises() -> None:
    probe = FfprobeMediaProbe(FakeProcessRunner(stdout="N/A"))

    with pytest.raises(InternalError):
        await probe.duration_sec("/video.mp4")


# --- segmenter -------------------------------------------------------------


async def test_segment_lists_produced_files(tmp_path: Path) -> None:
    (tmp_path / "conv_000.mp4").write_bytes(b"")
    (tmp_path / "conv_001.mp4").write_bytes(b"")
    runner = FakeProcessRunner()
    segmenter = FfmpegSegmenter(runner)

    produced = await segmenter.segment(
        str(tmp_path / "conv.mp4"),
        str(tmp_path / "conv_%03d.mp4"),
        segment_time=45,
    )

    assert produced == [
        str(tmp_path / "conv_000.mp4"),
        str(tmp_path / "conv_001.mp4"),
    ]
    assert "copy" in runner.calls[0]
    assert "segment" in runner.calls[0]
    # Гарантия нарезки по кейфрейму на границе сегмента (см. _SEGMENT_TIME_DELTA).
    assert "-segment_time_delta" in runner.calls[0]


async def test_segment_nonzero_raises(tmp_path: Path) -> None:
    segmenter = FfmpegSegmenter(FakeProcessRunner(returncode=1, stderr="broken"))

    with pytest.raises(SegmentFailedError):
        await segmenter.segment(
            str(tmp_path / "conv.mp4"), str(tmp_path / "c_%03d.mp4"), segment_time=45
        )


# --- transcoder ------------------------------------------------------------


async def test_transcode_emits_fractional_and_final_progress() -> None:
    runner = FakeProcessRunner(
        stdout_lines=[
            "out_time_us=5000000",
            "progress=continue",
            "out_time_us=10000000",
            "progress=end",
        ],
    )
    transcoder = FfmpegTranscoder(runner, FakeProbe(10.0))
    progress = ProgressCollector()

    await transcoder.transcode(
        "/source.mp4",
        "/conv.mp4",
        segment_time=45,
        fps=30,
        stories_fit=StoriesFit.NONE,
        on_progress=progress,
    )

    assert progress.events[0] == (0.5, None)
    assert progress.events[-1] == (1.0, None)
    assert "libx264" in runner.calls[0]
    assert "-vf" not in runner.calls[0]


@pytest.mark.parametrize(
    ("fit", "expected_flag"),
    [(StoriesFit.COVER, "-vf"), (StoriesFit.PAD, "-filter_complex")],
)
async def test_transcode_fit_filters(fit: StoriesFit, expected_flag: str) -> None:
    runner = FakeProcessRunner()
    transcoder = FfmpegTranscoder(runner, FakeProbe(10.0))

    await transcoder.transcode(
        "/source.mp4",
        "/conv.mp4",
        segment_time=45,
        fps=30,
        stories_fit=fit,
        on_progress=ProgressCollector(),
    )

    assert expected_flag in runner.calls[0]


async def test_transcode_without_duration_still_finishes() -> None:
    runner = FakeProcessRunner(stdout_lines=["out_time_us=5000000"])
    transcoder = FfmpegTranscoder(runner, FakeProbe(0.0, error=InternalError("no probe")))
    progress = ProgressCollector()

    await transcoder.transcode(
        "/source.mp4",
        "/conv.mp4",
        segment_time=45,
        fps=30,
        stories_fit=StoriesFit.NONE,
        on_progress=progress,
    )

    # Без длительности дробный прогресс не публикуется, но финальный 1.0 - да.
    assert progress.events == [(1.0, None)]


async def test_transcode_nonzero_raises() -> None:
    transcoder = FfmpegTranscoder(FakeProcessRunner(returncode=1, stderr="bad"), FakeProbe(10.0))

    with pytest.raises(TranscodeFailedError):
        await transcoder.transcode(
            "/source.mp4",
            "/conv.mp4",
            segment_time=45,
            fps=30,
            stories_fit=StoriesFit.NONE,
            on_progress=ProgressCollector(),
        )
