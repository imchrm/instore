"""Оркестрация конвейера обработки задачи.

``JobProcessingService.process`` последовательно выполняет фазы
download -> transcode -> segment -> probe -> ready, на каждой обновляя статус и
прогресс через шину событий и репозиторий. Любая доменная ошибка переводит
задачу в ``FAILED`` с соответствующим кодом.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from stories_backend.application.config import ProcessingLimits
from stories_backend.application.ports import Clock
from stories_backend.domain.entities import Chunk, Job, ProgressEvent, VideoMeta
from stories_backend.domain.enums import ErrorCode, JobStatus
from stories_backend.domain.errors import (
    AuthRequiredError,
    DomainError,
    TooLargeError,
    TooLongError,
)
from stories_backend.domain.ports import (
    CookiesStorePort,
    EventBusPort,
    JobRepositoryPort,
    MediaProbePort,
    ProgressCallback,
    SegmenterPort,
    StoragePort,
    TranscoderPort,
    VideoDownloaderPort,
)

_MB = 1024 * 1024
_CONV_NAME = "conv.mp4"
_SEGMENT_PATTERN = "conv_%03d.mp4"
_MANIFEST_NAME = "manifest.json"
_HASH_CHUNK = 1024 * 1024


class JobProcessingService:
    """Оркестратор фаз обработки одной задачи."""

    def __init__(
        self,
        *,
        repository: JobRepositoryPort,
        storage: StoragePort,
        event_bus: EventBusPort,
        downloader: VideoDownloaderPort,
        transcoder: TranscoderPort,
        segmenter: SegmenterPort,
        probe: MediaProbePort,
        cookies_store: CookiesStorePort,
        limits: ProcessingLimits,
        clock: Clock = time.time,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._event_bus = event_bus
        self._downloader = downloader
        self._transcoder = transcoder
        self._segmenter = segmenter
        self._probe = probe
        self._cookies_store = cookies_store
        self._limits = limits
        self._clock = clock

    async def process(self, job: Job) -> None:
        """Выполнить конвейер; любая ошибка переводит задачу в ``FAILED``."""
        try:
            await self._run_pipeline(job)
        except DomainError as error:
            await self._fail(job, error.code, error.message)
        except Exception as error:  # защита воркера: непредвиденное -> INTERNAL
            await self._fail(job, ErrorCode.INTERNAL, str(error))

    async def _run_pipeline(self, job: Job) -> None:
        cookies_path = await self._resolve_cookies(job)
        job_dir = self._storage.job_dir(job.job_id)

        await self._enter(job, JobStatus.DOWNLOADING)
        meta = await self._downloader.probe_meta(job.url, cookies_path=cookies_path)
        self._check_source_limits(meta)
        job.meta = meta
        source_path = await self._downloader.download(
            job.url,
            job_dir,
            max_height=job.max_height,
            max_filesize_mb=self._limits.max_filesize_mb,
            cookies_path=cookies_path,
            on_progress=self._progress(job, JobStatus.DOWNLOADING),
        )

        await self._enter(job, JobStatus.TRANSCODING)
        conv_path = str(Path(job_dir) / _CONV_NAME)
        await self._transcoder.transcode(
            source_path,
            conv_path,
            segment_time=job.segment_time,
            fps=self._limits.target_fps,
            stories_fit=job.stories_fit,
            on_progress=self._progress(job, JobStatus.TRANSCODING),
        )

        await self._enter(job, JobStatus.SEGMENTING)
        out_pattern = str(Path(job_dir) / _SEGMENT_PATTERN)
        chunk_paths = await self._segmenter.segment(
            conv_path, out_pattern, segment_time=job.segment_time
        )

        await self._enter(job, JobStatus.PROBING)
        job.chunks = await self._build_chunks(chunk_paths)
        await self._write_manifest(job, job_dir)
        await self._storage.remove_intermediate(job.job_id)

        await self._enter(job, JobStatus.READY, progress=1.0)

    async def _resolve_cookies(self, job: Job) -> str | None:
        if not job.use_cookies:
            return None
        path = await self._cookies_store.path(job.key_id)
        if path is None:
            msg = "требуются cookies, но файл для ключа отсутствует"
            raise AuthRequiredError(msg)
        return path

    def _check_source_limits(self, meta: VideoMeta) -> None:
        max_bytes = self._limits.max_filesize_mb * _MB
        if meta.filesize_bytes is not None and meta.filesize_bytes > max_bytes:
            msg = f"размер {meta.filesize_bytes} байт превышает лимит {max_bytes}"
            raise TooLargeError(msg)
        max_duration = self._limits.max_video_duration_sec
        if meta.duration_sec is not None and meta.duration_sec > max_duration:
            msg = f"длительность {meta.duration_sec} с превышает лимит {max_duration} с"
            raise TooLongError(msg)

    async def _build_chunks(self, chunk_paths: list[str]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for index, path in enumerate(chunk_paths):
            duration = await self._probe.duration_sec(path)
            size_bytes, sha256 = await asyncio.to_thread(_measure_file, path)
            chunks.append(
                Chunk(
                    index=index,
                    filename=Path(path).name,
                    duration_sec=duration,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    over_limit=duration > self._limits.keyframe_limit_sec,
                )
            )
        return chunks

    async def _write_manifest(self, job: Job, job_dir: str) -> None:
        manifest: dict[str, object] = {
            "job_id": job.job_id,
            "meta": None if job.meta is None else asdict(job.meta),
            "chunks": [asdict(chunk) for chunk in job.chunks],
        }
        path = str(Path(job_dir) / _MANIFEST_NAME)
        await asyncio.to_thread(_write_json, path, manifest)

    async def _enter(self, job: Job, status: JobStatus, *, progress: float = 0.0) -> None:
        job.transition_to(status)
        job.progress = progress
        if status is JobStatus.READY:
            job.updated_at = self._clock()
        await self._repository.update(job)
        await self._event_bus.publish(
            job.job_id,
            ProgressEvent(job_id=job.job_id, status=status, phase_progress=progress),
        )

    def _progress(self, job: Job, status: JobStatus) -> ProgressCallback:
        async def callback(fraction: float, message: str | None) -> None:
            job.progress = fraction
            await self._event_bus.publish(
                job.job_id,
                ProgressEvent(
                    job_id=job.job_id,
                    status=status,
                    phase_progress=fraction,
                    message=message,
                ),
            )

        return callback

    async def _fail(self, job: Job, code: ErrorCode, message: str) -> None:
        job.mark_failed(code, message)
        job.updated_at = self._clock()
        await self._repository.update(job)
        await self._event_bus.publish(
            job.job_id,
            ProgressEvent(
                job_id=job.job_id,
                status=JobStatus.FAILED,
                phase_progress=job.progress,
                message=message,
            ),
        )


def _measure_file(path: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _write_json(path: str, data: dict[str, object]) -> None:
    with Path(path).open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
