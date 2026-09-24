"""Integration-тест конвейера обработки на реальных ffmpeg/ffprobe.

Проверяет сквозной путь transcode -> segment -> probe -> ready на коротком
сгенерированном mp4. Скачивание подменяется локальным копированием файла
(``LocalFileDownloader``), чтобы не зависеть от сети и yt-dlp; всё остальное -
настоящие адаптеры инфраструктуры.

Требует установленных ``ffmpeg`` и ``ffprobe`` (иначе тест пропускается).
"""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from port_fakes import FakeCookiesStore, FakeEventBus, FakeJobRepository
from stories_backend.application.config import ProcessingLimits
from stories_backend.application.services.job_processing import JobProcessingService
from stories_backend.domain.entities import Job, ProgressEvent, VideoMeta
from stories_backend.domain.enums import JobStatus, StoriesFit
from stories_backend.domain.ports import ProgressCallback
from stories_backend.infrastructure.media.ffmpeg_segmenter import FfmpegSegmenter
from stories_backend.infrastructure.media.ffmpeg_transcoder import FfmpegTranscoder
from stories_backend.infrastructure.media.ffprobe_probe import FfprobeMediaProbe
from stories_backend.infrastructure.process.runner import AsyncioProcessRunner
from stories_backend.infrastructure.storage.filesystem_storage import FilesystemStorage

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _FFMPEG is None or _FFPROBE is None,
        reason="требуются установленные ffmpeg и ffprobe",
    ),
]

_SOURCE_DURATION_SEC = 12
_SEGMENT_TIME = 5
_KEYFRAME_LIMIT_SEC = 6


class LocalFileDownloader:
    """Заглушка ``VideoDownloaderPort``: копирует локальный файл как исходник."""

    def __init__(self, source: Path) -> None:
        self._source = source

    async def probe_meta(self, url: str, *, cookies_path: str | None) -> VideoMeta:
        return VideoMeta(
            title="testsrc",
            duration_sec=float(_SOURCE_DURATION_SEC),
            filesize_bytes=self._source.stat().st_size,
            height=240,
        )

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
        dest = Path(dest_dir) / "source.mp4"
        shutil.copyfile(self._source, dest)
        await on_progress(1.0, None)
        return str(dest)


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Сгенерировать короткий валидный mp4 (видео + звук) один раз на сессию."""
    out = tmp_path_factory.mktemp("fixtures") / "sample.mp4"
    argv = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={_SOURCE_DURATION_SEC}:size=320x240:rate=30",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=1000:duration={_SOURCE_DURATION_SEC}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(out),
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:  # pragma: no cover - диагностика сбоя генерации фикстуры
        pytest.fail(f"не удалось сгенерировать тестовый mp4: {result.stderr.strip()}")
    return out


def _build_service(
    tmp_path: Path,
    *,
    repo: FakeJobRepository,
    bus: FakeEventBus,
    storage: FilesystemStorage,
    downloader: LocalFileDownloader,
) -> JobProcessingService:
    runner = AsyncioProcessRunner()
    probe = FfprobeMediaProbe(runner)
    limits = ProcessingLimits(
        segment_time_default=_SEGMENT_TIME,
        keyframe_limit_sec=_KEYFRAME_LIMIT_SEC,
        target_fps=30,
    )
    return JobProcessingService(
        repository=repo,
        storage=storage,
        event_bus=bus,
        downloader=downloader,
        transcoder=FfmpegTranscoder(runner, probe),
        segmenter=FfmpegSegmenter(runner),
        probe=probe,
        cookies_store=FakeCookiesStore(),
        limits=limits,
    )


def _make_job() -> Job:
    return Job(
        job_id="job-int",
        key_id="phone",
        url="local://sample",
        segment_time=_SEGMENT_TIME,
        max_height=1080,
        stories_fit=StoriesFit.NONE,
        use_cookies=False,
        status=JobStatus.QUEUED,
    )


def _status_sequence(bus: FakeEventBus) -> list[JobStatus]:
    events: list[ProgressEvent] = [event for _job_id, event in bus.published]
    return [status for status, _group in itertools.groupby(e.status for e in events)]


async def test_pipeline_produces_bounded_chunks(sample_video: Path, tmp_path: Path) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    storage = FilesystemStorage(tmp_path)
    service = _build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=storage,
        downloader=LocalFileDownloader(sample_video),
    )
    job = _make_job()
    await repo.add(job)

    await service.process(job)

    assert job.status is JobStatus.READY, job.error_message
    assert job.progress == 1.0
    assert len(job.chunks) >= 2

    job_dir = Path(storage.job_dir(job.job_id))
    for index, chunk in enumerate(job.chunks):
        assert chunk.index == index
        chunk_file = job_dir / chunk.filename
        assert chunk_file.is_file()
        assert chunk.size_bytes == chunk_file.stat().st_size
        # Ключевая проверка фазы: все куски укладываются в лимит кейфреймов...
        assert 0.0 < chunk.duration_sec <= _KEYFRAME_LIMIT_SEC
        assert chunk.over_limit is False
        # ...и не превышают заданную длину сегмента (корректность кейфреймов).
        assert chunk.duration_sec <= _SEGMENT_TIME + 1.0

    # Суммарная длительность кусков близка к исходной длительности.
    total = sum(chunk.duration_sec for chunk in job.chunks)
    assert _SOURCE_DURATION_SEC - 1.5 <= total <= _SOURCE_DURATION_SEC + 1.5


async def test_pipeline_writes_manifest_and_removes_intermediate(
    sample_video: Path, tmp_path: Path
) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    storage = FilesystemStorage(tmp_path)
    service = _build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=storage,
        downloader=LocalFileDownloader(sample_video),
    )
    job = _make_job()
    await repo.add(job)

    await service.process(job)

    job_dir = Path(storage.job_dir(job.job_id))
    manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["job_id"] == job.job_id
    assert manifest["meta"]["title"] == "testsrc"
    assert len(manifest["chunks"]) == len(job.chunks)

    # Промежуточные файлы (source.* и conv.mp4) удаляются после probe.
    assert not (job_dir / "conv.mp4").exists()
    assert not list(job_dir.glob("source.*"))

    assert _status_sequence(bus) == [
        JobStatus.DOWNLOADING,
        JobStatus.TRANSCODING,
        JobStatus.SEGMENTING,
        JobStatus.PROBING,
        JobStatus.READY,
    ]
