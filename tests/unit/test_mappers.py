"""Тесты мапперов domain -> DTO."""

from __future__ import annotations

from stories_backend.application.config import ProcessingLimits
from stories_backend.domain.entities import Chunk, CookiesStatus, Job, ProgressEvent, VideoMeta
from stories_backend.domain.enums import ErrorCode, JobStatus, StoriesFit
from stories_backend.interface.api.mappers import (
    cookies_status_to_dto,
    job_to_response,
    limits_to_service_config,
    progress_event_to_dto,
)


def _chunk_url(job_id: str, index: int) -> str:
    return f"/api/v1/jobs/{job_id}/chunks/{index}"


def make_job(*, status: JobStatus, with_error: bool = False) -> Job:
    job = Job(
        job_id="job-1",
        key_id="phone",
        url="https://example.com/v",
        segment_time=45,
        max_height=1080,
        stories_fit=StoriesFit.NONE,
        use_cookies=False,
        status=status,
        progress=0.5,
        meta=VideoMeta(title="clip", duration_sec=42.0, filesize_bytes=1000, height=1080),
        chunks=[
            Chunk(
                index=0,
                filename="conv_000.mp4",
                duration_sec=45.0,
                size_bytes=10,
                sha256="ab",
                over_limit=False,
            )
        ],
        created_at=1.0,
        updated_at=2.0,
    )
    if with_error:
        job.error_code = ErrorCode.TOO_LARGE
        job.error_message = "слишком большой"
    return job


def test_job_to_response_maps_fields_and_chunk_url() -> None:
    response = job_to_response(make_job(status=JobStatus.READY), _chunk_url)

    assert response.job_id == "job-1"
    assert response.status is JobStatus.READY
    assert response.source_title == "clip"
    assert response.source_duration_sec == 42.0
    assert response.error is None
    assert len(response.chunks) == 1
    assert response.chunks[0].url == "/api/v1/jobs/job-1/chunks/0"


def test_job_to_response_includes_error() -> None:
    response = job_to_response(make_job(status=JobStatus.FAILED, with_error=True), _chunk_url)

    assert response.error is not None
    assert response.error.code is ErrorCode.TOO_LARGE
    assert response.error.message == "слишком большой"


def test_progress_event_to_dto() -> None:
    event = ProgressEvent(
        job_id="job-1", status=JobStatus.DOWNLOADING, phase_progress=0.3, message="idle"
    )
    dto = progress_event_to_dto(event)

    assert dto.job_id == "job-1"
    assert dto.status is JobStatus.DOWNLOADING
    assert dto.phase_progress == 0.3
    assert dto.message == "idle"


def test_cookies_status_to_dto() -> None:
    dto = cookies_status_to_dto(CookiesStatus(present=True, uploaded_at=5.0, likely_expired=True))

    assert dto.present is True
    assert dto.uploaded_at == 5.0
    assert dto.likely_expired is True


def test_limits_to_service_config_lists_all_fits() -> None:
    dto = limits_to_service_config(ProcessingLimits(max_filesize_mb=50, job_ttl_seconds=1200))

    assert dto.max_filesize_mb == 50
    assert dto.job_ttl_seconds == 1200
    assert dto.stories_fit_options == [StoriesFit.NONE, StoriesFit.COVER, StoriesFit.PAD]
