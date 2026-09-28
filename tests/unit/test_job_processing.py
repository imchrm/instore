"""Тесты оркестрации конвейера обработки задачи."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import pytest

from port_fakes import FakeCookiesStore, FakeEventBus, FakeJobRepository, FakeStorage
from stories_backend.application.config import ProcessingLimits
from stories_backend.application.services.job_processing import (
    JobProcessingService,
    plan_segment_seconds,
)
from stories_backend.application.use_cases.process_job import ProcessJobUseCase
from stories_backend.domain.entities import Job, VideoMeta
from stories_backend.domain.enums import ErrorCode, JobStatus, StoriesFit
from stories_backend.domain.errors import DomainError, DownloadFailedError
from stories_backend.domain.ports import ProgressCallback

_MB = 1024 * 1024


class FakeDownloader:
    """Заглушка ``VideoDownloaderPort``, создающая файл-исходник."""

    def __init__(
        self,
        meta: VideoMeta,
        *,
        probe_error: DomainError | None = None,
        download_error: DomainError | None = None,
    ) -> None:
        self._meta = meta
        self._probe_error = probe_error
        self._download_error = download_error

    async def probe_meta(self, url: str, *, cookies_path: str | None) -> VideoMeta:
        if self._probe_error is not None:
            raise self._probe_error
        return self._meta

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
        if self._download_error is not None:
            raise self._download_error
        source = Path(dest_dir) / "source.mp4"
        source.write_bytes(b"source")
        await on_progress(1.0, None)
        return str(source)


class FakeTranscoder:
    """Заглушка ``TranscoderPort``, создающая перекодированный файл."""

    async def transcode(
        self,
        src: str,
        dest: str,
        *,
        segment_time: float,
        fps: int,
        stories_fit: StoriesFit,
        on_progress: ProgressCallback,
    ) -> None:
        Path(dest).write_bytes(b"converted")
        await on_progress(1.0, None)


class FakeSegmenter:
    """Заглушка ``SegmenterPort``, создающая куски с известным содержимым."""

    def __init__(self, contents: list[bytes]) -> None:
        self._contents = contents
        self.segment_time_used: float | None = None

    async def segment(self, src: str, out_pattern: str, *, segment_time: float) -> list[str]:
        self.segment_time_used = segment_time
        parent = Path(out_pattern).parent
        paths: list[str] = []
        for index, content in enumerate(self._contents):
            chunk = parent / f"conv_{index:03d}.mp4"
            chunk.write_bytes(content)
            paths.append(str(chunk))
        return paths


class FakeProbe:
    """Заглушка ``MediaProbePort``.

    Для исходника (``source.*``) возвращает ``source_duration`` - его меряет
    планировщик нарезки; для остальных путей отдаёт длительности кусков по
    порядку.
    """

    def __init__(self, durations: list[float], *, source_duration: float = 10.0) -> None:
        self._durations = iter(durations)
        self._source_duration = source_duration

    async def duration_sec(self, path: str) -> float:
        if Path(path).name.startswith("source"):
            return self._source_duration
        return next(self._durations)


def make_job(*, use_cookies: bool = False) -> Job:
    return Job(
        job_id="job-1",
        key_id="phone",
        url="https://example.com/v",
        segment_time=45,
        max_height=1080,
        stories_fit=StoriesFit.NONE,
        use_cookies=use_cookies,
        status=JobStatus.QUEUED,
    )


def build_service(
    tmp_path: Path,
    *,
    repo: FakeJobRepository,
    bus: FakeEventBus,
    storage: FakeStorage,
    cookies: FakeCookiesStore,
    downloader: FakeDownloader,
    segmenter: FakeSegmenter | None = None,
    probe: FakeProbe | None = None,
    limits: ProcessingLimits | None = None,
) -> JobProcessingService:
    return JobProcessingService(
        repository=repo,
        storage=storage,
        event_bus=bus,
        downloader=downloader,
        transcoder=FakeTranscoder(),
        segmenter=segmenter or FakeSegmenter([b"chunk-0", b"chunk-1"]),
        probe=probe or FakeProbe([30.0, 30.0]),
        cookies_store=cookies,
        limits=limits or ProcessingLimits(),
        clock=lambda: 777.0,
    )


def status_sequence(bus: FakeEventBus) -> list[JobStatus]:
    """Последовательность статусов событий без подряд идущих повторов."""
    return [status for status, _group in itertools.groupby(e.status for _job, e in bus.published)]


async def test_happy_path_produces_ready_with_chunks(tmp_path: Path) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    storage = FakeStorage(base_dir=tmp_path)
    cookies = FakeCookiesStore()
    meta = VideoMeta(title="clip", duration_sec=90.0, filesize_bytes=10 * _MB, height=1080)
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=storage,
        cookies=cookies,
        downloader=FakeDownloader(meta),
    )
    job = make_job()
    await repo.add(job)

    await service.process(job)

    assert job.status is JobStatus.READY
    assert job.progress == 1.0
    assert job.updated_at == 777.0
    assert [chunk.filename for chunk in job.chunks] == ["conv_000.mp4", "conv_001.mp4"]
    assert [chunk.over_limit for chunk in job.chunks] == [False, False]
    assert job.chunks[0].sha256 == hashlib.sha256(b"chunk-0").hexdigest()
    assert job.chunks[0].size_bytes == len(b"chunk-0")

    manifest_path = tmp_path / "job-1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["job_id"] == "job-1"
    assert len(manifest["chunks"]) == 2

    assert storage.removed_intermediate == ["job-1"]
    assert status_sequence(bus) == [
        JobStatus.DOWNLOADING,
        JobStatus.TRANSCODING,
        JobStatus.SEGMENTING,
        JobStatus.PROBING,
        JobStatus.READY,
    ]


async def test_over_limit_chunk_is_flagged(tmp_path: Path) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    meta = VideoMeta(title=None, duration_sec=None, filesize_bytes=None, height=None)
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=FakeStorage(base_dir=tmp_path),
        cookies=FakeCookiesStore(),
        downloader=FakeDownloader(meta),
        probe=FakeProbe([70.0, 30.0]),
    )
    job = make_job()
    await repo.add(job)

    await service.process(job)

    assert [chunk.over_limit for chunk in job.chunks] == [True, False]


async def test_missing_cookies_fail_auth_required(tmp_path: Path) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    meta = VideoMeta(title=None, duration_sec=None, filesize_bytes=None, height=None)
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=FakeStorage(base_dir=tmp_path),
        cookies=FakeCookiesStore(),
        downloader=FakeDownloader(meta),
    )
    job = make_job(use_cookies=True)
    await repo.add(job)

    await service.process(job)

    assert job.status is JobStatus.FAILED
    assert job.error_code is ErrorCode.AUTH_REQUIRED
    assert status_sequence(bus) == [JobStatus.FAILED]


async def test_too_large_fails(tmp_path: Path) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    meta = VideoMeta(title=None, duration_sec=None, filesize_bytes=100 * _MB, height=None)
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=FakeStorage(base_dir=tmp_path),
        cookies=FakeCookiesStore(),
        downloader=FakeDownloader(meta),
        limits=ProcessingLimits(max_filesize_mb=50),
    )
    job = make_job()
    await repo.add(job)

    await service.process(job)

    assert job.status is JobStatus.FAILED
    assert job.error_code is ErrorCode.TOO_LARGE


async def test_too_long_fails(tmp_path: Path) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    meta = VideoMeta(title=None, duration_sec=5000.0, filesize_bytes=None, height=None)
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=FakeStorage(base_dir=tmp_path),
        cookies=FakeCookiesStore(),
        downloader=FakeDownloader(meta),
        limits=ProcessingLimits(max_video_duration_sec=1800),
    )
    job = make_job()
    await repo.add(job)

    await service.process(job)

    assert job.status is JobStatus.FAILED
    assert job.error_code is ErrorCode.TOO_LONG


async def test_download_failure_maps_to_failed(tmp_path: Path) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    meta = VideoMeta(title=None, duration_sec=None, filesize_bytes=None, height=None)
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=FakeStorage(base_dir=tmp_path),
        cookies=FakeCookiesStore(),
        downloader=FakeDownloader(meta, download_error=DownloadFailedError("сеть упала")),
    )
    job = make_job()
    await repo.add(job)

    await service.process(job)

    assert job.status is JobStatus.FAILED
    assert job.error_code is ErrorCode.DOWNLOAD_FAILED


async def test_process_job_use_case_runs_service(tmp_path: Path) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    meta = VideoMeta(title=None, duration_sec=None, filesize_bytes=None, height=None)
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=FakeStorage(base_dir=tmp_path),
        cookies=FakeCookiesStore(),
        downloader=FakeDownloader(meta),
    )
    job = make_job()
    await repo.add(job)
    use_case = ProcessJobUseCase(repo, service)

    await use_case.execute("job-1")
    assert job.status is JobStatus.READY

    # Несуществующая задача не приводит к ошибке.
    await use_case.execute("absent")


@pytest.mark.parametrize("missing", ["absent"])
async def test_process_job_use_case_missing_is_noop(tmp_path: Path, missing: str) -> None:
    repo = FakeJobRepository()
    bus = FakeEventBus()
    meta = VideoMeta(title=None, duration_sec=None, filesize_bytes=None, height=None)
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=FakeStorage(base_dir=tmp_path),
        cookies=FakeCookiesStore(),
        downloader=FakeDownloader(meta),
    )
    use_case = ProcessJobUseCase(repo, service)

    await use_case.execute(missing)
    assert bus.published == []


# --- планировщик длины сегмента --------------------------------------------


def test_plan_no_split_when_within_limit() -> None:
    # Ролик короче предела -> один кусок (граница нарезки за пределом видео).
    seg = plan_segment_seconds(47.0, limit_sec=60, target_sec=45)
    assert seg > 47.0


def test_plan_boundary_equal_limit_is_single() -> None:
    seg = plan_segment_seconds(60.0, limit_sec=60, target_sec=45)
    assert seg > 60.0


def test_plan_even_split_avoids_tiny_tail() -> None:
    # 92 c при цели 45 -> 3 равные части ~30.7 c, а не 45+45+2.
    seg = plan_segment_seconds(92.0, limit_sec=60, target_sec=45)
    assert seg <= 45.0
    assert round(92.0 / seg) == 3
    assert abs(seg - 92.0 / 3) < 1e-6


def test_plan_keeps_under_limit_with_large_target() -> None:
    # Большая цель ограничивается пределом и запасом: 120 c -> 3 части по 40.
    seg = plan_segment_seconds(120.0, limit_sec=60, target_sec=100)
    assert seg <= 60 - 0.5
    assert round(120.0 / seg) == 3


def test_plan_zero_duration_is_single() -> None:
    assert plan_segment_seconds(0.0, limit_sec=60, target_sec=45) == 1.0


async def test_pipeline_plans_segment_from_source_duration(tmp_path: Path) -> None:
    # Оркестратор берёт длительность исходника (source_duration) и передаёт
    # планированную длину сегмента в segmenter.
    repo = FakeJobRepository()
    bus = FakeEventBus()
    meta = VideoMeta(title=None, duration_sec=None, filesize_bytes=None, height=None)
    segmenter = FakeSegmenter([b"c0"])
    service = build_service(
        tmp_path,
        repo=repo,
        bus=bus,
        storage=FakeStorage(base_dir=tmp_path),
        cookies=FakeCookiesStore(),
        downloader=FakeDownloader(meta),
        segmenter=segmenter,
        probe=FakeProbe([10.0], source_duration=30.0),
        limits=ProcessingLimits(keyframe_limit_sec=60, segment_time_default=45),
    )
    job = make_job()
    await repo.add(job)

    await service.process(job)

    assert job.status is JobStatus.READY
    # 30 c <= 60 -> один кусок: сегмент больше длительности исходника.
    assert segmenter.segment_time_used is not None
    assert segmenter.segment_time_used > 30.0
