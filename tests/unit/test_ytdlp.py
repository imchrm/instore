"""Тесты адаптера скачивания yt-dlp на фейковом раннере процессов."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from stories_backend.domain.errors import (
    AuthRequiredError,
    DomainError,
    DownloadFailedError,
    TooLargeError,
    VideoPrivateError,
    VideoUnavailableError,
)
from stories_backend.infrastructure.downloader.ytdlp import YtDlpDownloader
from stories_backend.infrastructure.process.runner import LineCallback, ProcessResult


class FakeProcessRunner:
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


class ProgressCollector:
    def __init__(self) -> None:
        self.events: list[tuple[float, str | None]] = []

    async def __call__(self, fraction: float, message: str | None) -> None:
        self.events.append((fraction, message))


# --- probe_meta ------------------------------------------------------------


async def test_probe_meta_parses_json() -> None:
    info = {"title": "clip", "duration": 42.0, "filesize": 1000, "height": 1080}
    runner = FakeProcessRunner(stdout=json.dumps(info))
    downloader = YtDlpDownloader(runner)

    meta = await downloader.probe_meta("https://example.com/v", cookies_path=None)

    assert meta.title == "clip"
    assert meta.duration_sec == 42.0
    assert meta.filesize_bytes == 1000
    assert meta.height == 1080
    assert "-J" in runner.calls[0]
    assert "--cookies" not in runner.calls[0]


async def test_probe_meta_uses_filesize_approx_and_cookies() -> None:
    info = {"title": "clip", "duration": 10.0, "filesize_approx": 555, "height": 720}
    runner = FakeProcessRunner(stdout=json.dumps(info))
    downloader = YtDlpDownloader(runner)

    meta = await downloader.probe_meta("https://example.com/v", cookies_path="/c/phone.txt")

    assert meta.filesize_bytes == 555
    assert runner.calls[0].count("--cookies") == 1
    assert "/c/phone.txt" in runner.calls[0]


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("ERROR: This video is private", VideoPrivateError),
        ("ERROR: Sign in to confirm your age", AuthRequiredError),
        ("ERROR: Video unavailable", VideoUnavailableError),
        ("ERROR: File is larger than max-filesize", TooLargeError),
        ("ERROR: something totally unexpected", DownloadFailedError),
    ],
)
async def test_probe_meta_error_mapping(stderr: str, expected: type[DomainError]) -> None:
    downloader = YtDlpDownloader(FakeProcessRunner(returncode=1, stderr=stderr))

    with pytest.raises(expected):
        await downloader.probe_meta("https://example.com/v", cookies_path=None)


async def test_probe_meta_bad_json_raises() -> None:
    downloader = YtDlpDownloader(FakeProcessRunner(stdout="not-json"))

    with pytest.raises(DownloadFailedError):
        await downloader.probe_meta("https://example.com/v", cookies_path=None)


# --- download --------------------------------------------------------------


async def test_download_returns_source_path_and_progress(tmp_path: Path) -> None:
    (tmp_path / "source.mp4").write_bytes(b"data")
    runner = FakeProcessRunner(
        stdout_lines=["[download]  50.0% of 10MiB", "[download] 100.0% of 10MiB"]
    )
    downloader = YtDlpDownloader(runner)
    progress = ProgressCollector()

    result = await downloader.download(
        "https://example.com/v",
        str(tmp_path),
        max_height=1080,
        max_filesize_mb=50,
        cookies_path=None,
        on_progress=progress,
    )

    assert result == str(tmp_path / "source.mp4")
    assert (0.5, None) in progress.events
    assert progress.events[-1] == (1.0, None)
    assert "--max-filesize" in runner.calls[0]
    assert "50M" in runner.calls[0]


async def test_download_ignores_part_files(tmp_path: Path) -> None:
    (tmp_path / "source.mp4.part").write_bytes(b"partial")
    (tmp_path / "source.mp4").write_bytes(b"data")
    downloader = YtDlpDownloader(FakeProcessRunner())

    result = await downloader.download(
        "https://example.com/v",
        str(tmp_path),
        max_height=720,
        max_filesize_mb=50,
        cookies_path=None,
        on_progress=ProgressCollector(),
    )

    assert result == str(tmp_path / "source.mp4")


async def test_download_missing_source_raises(tmp_path: Path) -> None:
    downloader = YtDlpDownloader(FakeProcessRunner())

    with pytest.raises(DownloadFailedError):
        await downloader.download(
            "https://example.com/v",
            str(tmp_path),
            max_height=1080,
            max_filesize_mb=50,
            cookies_path=None,
            on_progress=ProgressCollector(),
        )


async def test_download_error_mapping(tmp_path: Path) -> None:
    downloader = YtDlpDownloader(
        FakeProcessRunner(returncode=1, stderr="ERROR: File is larger than max-filesize"),
    )

    with pytest.raises(TooLargeError):
        await downloader.download(
            "https://example.com/v",
            str(tmp_path),
            max_height=1080,
            max_filesize_mb=50,
            cookies_path=None,
            on_progress=ProgressCollector(),
        )
