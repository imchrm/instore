"""Тесты роутеров jobs/admin на приложении с fake-контейнером."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from port_fakes import (
    FakeCookiesStore,
    FakeEventBus,
    FakeJobRepository,
    FakeJobSubmitter,
    FakeStorage,
)
from stories_backend.application.use_cases.cookies_admin import CookiesAdminUseCase
from stories_backend.application.use_cases.create_job import CreateJobUseCase
from stories_backend.application.use_cases.delete_job import DeleteJobUseCase
from stories_backend.application.use_cases.get_job import GetJobUseCase
from stories_backend.application.use_cases.get_job_unscoped import GetJobUnscopedUseCase
from stories_backend.application.use_cases.stream_progress import StreamProgressUseCase
from stories_backend.domain.entities import Chunk, Job, ProgressEvent
from stories_backend.domain.enums import JobStatus, StoriesFit
from stories_backend.infrastructure.security.api_keys import ApiKeyRegistry
from stories_backend.infrastructure.security.url_signer import UrlSigner
from stories_backend.interface.api.container import Container
from stories_backend.interface.api.routers import admin, jobs
from stories_backend.interface.api.routers.jobs import _sse_stream
from stories_backend.interface.config import Settings

_HEADERS = {"X-API-Key": "secret-phone"}


class Harness:
    """Собранное тестовое приложение и его fake-зависимости."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        use_xaccel: bool = False,
        root_path: str = "",
        signing_secret: str = "",
        public_base_url: str = "",
    ) -> None:
        self.repo = FakeJobRepository()
        self.storage = FakeStorage(base_dir=tmp_path)
        self.bus = FakeEventBus()
        self.cookies = FakeCookiesStore()
        self.submitter = FakeJobSubmitter()
        settings = Settings(
            api_keys="Phone:secret-phone, Tablet:secret-tablet",
            data_dir=str(tmp_path),
            use_xaccel=use_xaccel,
            root_path=root_path,
            signing_secret=signing_secret,
            public_base_url=public_base_url,
        )
        container = Container(
            settings=settings,
            limits=settings.to_limits(),
            api_keys=ApiKeyRegistry.from_config(settings.api_keys),
            storage=self.storage,
            create_job=CreateJobUseCase(self.repo, self.submitter, id_generator=lambda: "job-1"),
            get_job=GetJobUseCase(self.repo),
            get_job_unscoped=GetJobUnscopedUseCase(self.repo),
            delete_job=DeleteJobUseCase(self.repo, self.storage),
            stream_progress=StreamProgressUseCase(self.repo, self.bus),
            cookies_admin=CookiesAdminUseCase(self.cookies),
            url_signer=UrlSigner(signing_secret) if signing_secret else None,
        )
        app = FastAPI()
        app.state.container = container
        app.include_router(jobs.router)
        app.include_router(admin.router)
        self.client = TestClient(app)


def make_job(
    job_id: str, key_id: str, *, status: JobStatus, chunks: list[Chunk] | None = None
) -> Job:
    return Job(
        job_id=job_id,
        key_id=key_id,
        url="https://example.com/v",
        segment_time=45,
        max_height=1080,
        stories_fit=StoriesFit.NONE,
        use_cookies=False,
        status=status,
        chunks=chunks or [],
    )


# --- POST /jobs ------------------------------------------------------------


def test_create_job_requires_api_key(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    response = harness.client.post("/api/v1/jobs", json={"url": "https://example.com/v"})
    assert response.status_code == 401


def test_create_job_rejects_invalid_key(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    response = harness.client.post(
        "/api/v1/jobs",
        json={"url": "https://example.com/v"},
        headers={"X-API-Key": "nope"},
    )
    assert response.status_code == 401


def test_create_job_ok(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    response = harness.client.post(
        "/api/v1/jobs",
        json={"url": "https://example.com/v", "stories_fit": "cover"},
        headers=_HEADERS,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == "job-1"
    assert body["status"] == "queued"
    assert harness.submitter.submitted == ["job-1"]
    assert harness.repo.jobs["job-1"].key_id == "phone"
    assert harness.repo.jobs["job-1"].stories_fit is StoriesFit.COVER


def test_create_job_validates_body(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    response = harness.client.post(
        "/api/v1/jobs",
        json={"url": "not-a-url"},
        headers=_HEADERS,
    )
    assert response.status_code == 422


# --- GET / DELETE /jobs/{id} ----------------------------------------------


def test_get_job_isolated_by_key(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.repo.jobs["job-1"] = make_job("job-1", "phone", status=JobStatus.READY)

    own = harness.client.get("/api/v1/jobs/job-1", headers=_HEADERS)
    assert own.status_code == 200
    assert own.json()["status"] == "ready"

    foreign = harness.client.get("/api/v1/jobs/job-1", headers={"X-API-Key": "secret-tablet"})
    assert foreign.status_code == 404


def test_get_job_chunk_url_without_prefix(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.repo.jobs["job-1"] = _job_with_chunk()

    body = harness.client.get("/api/v1/jobs/job-1", headers=_HEADERS).json()

    assert body["chunks"][0]["url"] == "/api/v1/jobs/job-1/chunks/0"


def test_get_job_chunk_url_uses_root_path(tmp_path: Path) -> None:
    harness = Harness(tmp_path, root_path="/instore")
    harness.repo.jobs["job-1"] = _job_with_chunk()

    body = harness.client.get("/api/v1/jobs/job-1", headers=_HEADERS).json()

    assert body["chunks"][0]["url"] == "/instore/api/v1/jobs/job-1/chunks/0"


def test_delete_job(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.repo.jobs["job-1"] = make_job("job-1", "phone", status=JobStatus.READY)

    deleted = harness.client.delete("/api/v1/jobs/job-1", headers=_HEADERS)
    assert deleted.status_code == 204
    assert harness.storage.removed_jobs == ["job-1"]

    again = harness.client.delete("/api/v1/jobs/job-1", headers=_HEADERS)
    assert again.status_code == 404


# --- chunks ----------------------------------------------------------------


def _job_with_chunk() -> Job:
    chunk = Chunk(
        index=0,
        filename="conv_000.mp4",
        duration_sec=45.0,
        size_bytes=7,
        sha256="ab",
        over_limit=False,
    )
    return make_job("job-1", "phone", status=JobStatus.READY, chunks=[chunk])


def test_get_chunk_file_response(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.repo.jobs["job-1"] = _job_with_chunk()
    job_dir = Path(harness.storage.job_dir("job-1"))
    (job_dir / "conv_000.mp4").write_bytes(b"chunk-0")

    response = harness.client.get("/api/v1/jobs/job-1/chunks/0", headers=_HEADERS)

    assert response.status_code == 200
    assert response.content == b"chunk-0"
    assert response.headers["content-type"] == "video/mp4"


def test_get_chunk_xaccel(tmp_path: Path) -> None:
    harness = Harness(tmp_path, use_xaccel=True)
    harness.repo.jobs["job-1"] = _job_with_chunk()

    response = harness.client.get("/api/v1/jobs/job-1/chunks/0", headers=_HEADERS)

    assert response.status_code == 200
    assert response.headers["X-Accel-Redirect"] == "/_protected/job-1/conv_000.mp4"


def test_get_chunk_missing_index(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.repo.jobs["job-1"] = _job_with_chunk()

    response = harness.client.get("/api/v1/jobs/job-1/chunks/9", headers=_HEADERS)
    assert response.status_code == 404


# --- size-guard (over_story_limit) ----------------------------------------


def test_job_response_flags_over_story_limit(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    big = Chunk(
        index=0,
        filename="conv_000.mp4",
        duration_sec=45.0,
        size_bytes=40 * 1024 * 1024,  # > 30 МБ лимита Stories
        sha256="ab",
        over_limit=False,
    )
    harness.repo.jobs["job-1"] = make_job("job-1", "phone", status=JobStatus.READY, chunks=[big])

    body = harness.client.get("/api/v1/jobs/job-1", headers=_HEADERS).json()

    assert body["chunks"][0]["over_story_limit"] is True


# --- signed share URLs -----------------------------------------------------

_SECRET = "test-signing-secret"


def test_mint_share_url_disabled_without_secret(tmp_path: Path) -> None:
    harness = Harness(tmp_path)  # signing_secret пуст -> функция выключена
    harness.repo.jobs["job-1"] = _job_with_chunk()

    response = harness.client.get("/api/v1/jobs/job-1/chunks/0/share-url", headers=_HEADERS)
    assert response.status_code == 503


def test_mint_share_url_ok(tmp_path: Path) -> None:
    harness = Harness(tmp_path, signing_secret=_SECRET, public_base_url="https://host/instore")
    harness.repo.jobs["job-1"] = _job_with_chunk()

    response = harness.client.get("/api/v1/jobs/job-1/chunks/0/share-url", headers=_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("https://host/instore/api/v1/public/chunks/job-1/0?")
    assert "exp=" in body["url"] and "sig=" in body["url"]
    assert body["expires_at"] > int(time.time())


def test_mint_share_url_requires_ownership(tmp_path: Path) -> None:
    harness = Harness(tmp_path, signing_secret=_SECRET)
    harness.repo.jobs["job-1"] = _job_with_chunk()

    foreign = harness.client.get(
        "/api/v1/jobs/job-1/chunks/0/share-url", headers={"X-API-Key": "secret-tablet"}
    )
    assert foreign.status_code == 404


def test_public_chunk_serves_with_valid_signature(tmp_path: Path) -> None:
    harness = Harness(tmp_path, signing_secret=_SECRET)
    harness.repo.jobs["job-1"] = _job_with_chunk()
    job_dir = Path(harness.storage.job_dir("job-1"))
    (job_dir / "conv_000.mp4").write_bytes(b"chunk-0")

    exp = int(time.time()) + 300
    sig = UrlSigner(_SECRET).sign("job-1", 0, exp)
    response = harness.client.get(f"/api/v1/public/chunks/job-1/0?exp={exp}&sig={sig}")

    assert response.status_code == 200
    assert response.content == b"chunk-0"


def test_public_chunk_rejects_bad_signature(tmp_path: Path) -> None:
    harness = Harness(tmp_path, signing_secret=_SECRET)
    harness.repo.jobs["job-1"] = _job_with_chunk()

    exp = int(time.time()) + 300
    response = harness.client.get(f"/api/v1/public/chunks/job-1/0?exp={exp}&sig=wrong")
    assert response.status_code == 403


def test_public_chunk_rejects_expired(tmp_path: Path) -> None:
    harness = Harness(tmp_path, signing_secret=_SECRET)
    harness.repo.jobs["job-1"] = _job_with_chunk()

    exp = int(time.time()) - 1
    sig = UrlSigner(_SECRET).sign("job-1", 0, exp)
    response = harness.client.get(f"/api/v1/public/chunks/job-1/0?exp={exp}&sig={sig}")
    assert response.status_code == 403


def test_public_chunk_disabled_without_secret(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.repo.jobs["job-1"] = _job_with_chunk()

    response = harness.client.get("/api/v1/public/chunks/job-1/0?exp=1&sig=x")
    assert response.status_code == 404


# --- SSE -------------------------------------------------------------------


def test_stream_events_missing_job(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    response = harness.client.get("/api/v1/jobs/absent/events", headers=_HEADERS)
    assert response.status_code == 404


# --- admin cookies ---------------------------------------------------------


def test_cookies_upload_status_delete(tmp_path: Path) -> None:
    harness = Harness(tmp_path)

    absent = harness.client.get("/api/v1/admin/cookies/status", headers=_HEADERS)
    assert absent.status_code == 200
    assert absent.json()["present"] is False

    uploaded = harness.client.post(
        "/api/v1/admin/cookies", content=b"cookie-data", headers=_HEADERS
    )
    assert uploaded.status_code == 204
    assert harness.cookies.saved["phone"] == b"cookie-data"

    present = harness.client.get("/api/v1/admin/cookies/status", headers=_HEADERS)
    assert present.json()["present"] is True

    removed = harness.client.delete("/api/v1/admin/cookies", headers=_HEADERS)
    assert removed.status_code == 204
    assert harness.cookies.deleted == ["phone"]


def test_cookies_requires_api_key(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    response = harness.client.get("/api/v1/admin/cookies/status")
    assert response.status_code == 401


# --- _sse_stream -----------------------------------------------------------


async def test_sse_stream_stops_on_terminal_status() -> None:
    async def events() -> AsyncIterator[ProgressEvent]:
        yield ProgressEvent(job_id="job-1", status=JobStatus.DOWNLOADING, phase_progress=0.5)
        yield ProgressEvent(job_id="job-1", status=JobStatus.READY, phase_progress=1.0)
        yield ProgressEvent(job_id="job-1", status=JobStatus.PROBING, phase_progress=0.9)

    chunks = [chunk async for chunk in _sse_stream(events())]

    assert len(chunks) == 2
    assert chunks[0].startswith("data: ")
    assert chunks[0].endswith("\n\n")
    assert '"status":"ready"' in chunks[1]
