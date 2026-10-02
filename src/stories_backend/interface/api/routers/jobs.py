"""Роутер задач: создание, статус/манифест, удаление, SSE-прогресс, отдача кусков."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from stories_backend.application.use_cases.create_job import CreateJobCommand
from stories_backend.domain.entities import Chunk, Job, ProgressEvent
from stories_backend.domain.enums import JobStatus
from stories_backend.interface.api.container import Container
from stories_backend.interface.api.deps import ContainerDep, KeyIdDep
from stories_backend.interface.api.mappers import (
    ChunkUrlBuilder,
    job_to_response,
    progress_event_to_dto,
)
from stories_backend.interface.api.schemas import JobCreateRequest, JobResponse, ShareUrlDto

router = APIRouter(prefix="/api/v1", tags=["jobs"])

_CHUNK_MEDIA_TYPE = "video/mp4"
_MIB = 1024 * 1024
_TERMINAL_STATUSES = frozenset({JobStatus.READY, JobStatus.FAILED, JobStatus.EXPIRED})


def _story_max_bytes(container: Container) -> int:
    return container.limits.story_max_filesize_mb * _MIB


def _find_chunk(job: Job, index: int) -> Chunk | None:
    return next((item for item in job.chunks if item.index == index), None)


def _serve_chunk_response(container: Container, job_id: str, filename: str) -> Response:
    """Отдать файл куска: через X-Accel-Redirect (prod) или FileResponse (dev)."""
    settings = container.settings
    if settings.use_xaccel:
        internal = f"{settings.xaccel_internal_prefix}/{job_id}/{filename}"
        return Response(headers={"X-Accel-Redirect": internal}, media_type=_CHUNK_MEDIA_TYPE)
    path = Path(container.storage.job_dir(job_id)) / filename
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="файл куска отсутствует")
    return FileResponse(path, media_type=_CHUNK_MEDIA_TYPE)


def _chunk_url_builder(root_path: str) -> ChunkUrlBuilder:
    """Построитель URL куска с учётом публичного префикса за reverse-proxy.

    При ``root_path='/instore'`` вернёт ``/instore/api/v1/jobs/{id}/chunks/{index}``,
    при пустом префиксе - ``/api/v1/jobs/{id}/chunks/{index}``.
    """

    def build(job_id: str, index: int) -> str:
        return f"{root_path}/api/v1/jobs/{job_id}/chunks/{index}"

    return build


async def _sse_stream(events: AsyncIterator[ProgressEvent]) -> AsyncIterator[str]:
    """Обернуть поток событий в формат SSE; закрыть подписку по завершении."""
    try:
        async for event in events:
            yield f"data: {progress_event_to_dto(event).model_dump_json()}\n\n"
            if event.status in _TERMINAL_STATUSES:
                return
    finally:
        aclose = getattr(events, "aclose", None)
        if aclose is not None:
            await aclose()


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse)
async def create_job(
    payload: JobCreateRequest, container: ContainerDep, key_id: KeyIdDep
) -> JobResponse:
    """Создать задачу и поставить её в очередь обработки."""
    command = CreateJobCommand(
        key_id=key_id,
        url=str(payload.url),
        segment_time=payload.segment_time,
        max_height=payload.max_height,
        stories_fit=payload.stories_fit,
        use_cookies=payload.use_cookies,
    )
    job = await container.create_job.execute(command)
    return job_to_response(
        job, _chunk_url_builder(container.settings.root_path), _story_max_bytes(container)
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, container: ContainerDep, key_id: KeyIdDep) -> JobResponse:
    """Вернуть статус/манифест задачи текущего ключа."""
    job = await container.get_job.execute(job_id, key_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="задача не найдена")
    return job_to_response(
        job, _chunk_url_builder(container.settings.root_path), _story_max_bytes(container)
    )


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, container: ContainerDep, key_id: KeyIdDep) -> Response:
    """Удалить задачу и её файлы."""
    deleted = await container.delete_job.execute(job_id, key_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="задача не найдена")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}/events")
async def stream_events(
    job_id: str, container: ContainerDep, key_id: KeyIdDep
) -> StreamingResponse:
    """Поток прогресса задачи в формате SSE."""
    stream = await container.stream_progress.execute(job_id, key_id)
    if stream is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="задача не найдена")
    return StreamingResponse(_sse_stream(stream), media_type="text/event-stream")


@router.get("/jobs/{job_id}/chunks/{index}/share-url", response_model=ShareUrlDto)
async def mint_share_url(
    job_id: str, index: int, request: Request, container: ContainerDep, key_id: KeyIdDep
) -> ShareUrlDto:
    """Выдать подписанную публичную ссылку на кусок (для Telegram shareToStory).

    Требует владения задачей (по ``X-API-Key``). Сама ссылка затем доступна без
    ключа - авторизацией служит HMAC-подпись с ограниченным сроком действия.
    """
    signer = container.url_signer
    if signer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="подписанные URL не настроены (SIGNING_SECRET)",
        )
    job = await container.get_job.execute(job_id, key_id)
    if job is None or job.status is not JobStatus.READY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="задача не найдена")
    if _find_chunk(job, index) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="кусок не найден")

    expires_at = int(time.time()) + container.settings.signed_url_ttl_sec
    signature = signer.sign(job_id, index, expires_at)
    url = _public_chunk_url(request, container, job_id, index, exp=expires_at, sig=signature)
    return ShareUrlDto(url=url, expires_at=expires_at)


@router.get("/jobs/{job_id}/chunks/{index}")
async def get_chunk(job_id: str, index: int, container: ContainerDep, key_id: KeyIdDep) -> Response:
    """Отдать файл куска по ключу (владельцу задачи)."""
    job = await container.get_job.execute(job_id, key_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="задача не найдена")
    chunk = _find_chunk(job, index)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="кусок не найден")
    return _serve_chunk_response(container, job_id, chunk.filename)


@router.get("/public/chunks/{job_id}/{index}", name="serve_public_chunk")
async def serve_public_chunk(
    job_id: str, index: int, exp: int, sig: str, container: ContainerDep
) -> Response:
    """Публичная отдача куска по подписанной ссылке (без X-API-Key).

    Авторизация - валидная HMAC-подпись и неистёкший срок. Нужна внешним
    сервисам, которые тянут файл сами (Telegram shareToStory).
    """
    signer = container.url_signer
    if signer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if exp < int(time.time()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ссылка истекла")
    if not signer.verify(job_id, index, exp, sig):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="неверная подпись")

    job = await container.get_job_unscoped.execute(job_id)
    if job is None or job.status is not JobStatus.READY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="задача не найдена")
    chunk = _find_chunk(job, index)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="кусок не найден")
    return _serve_chunk_response(container, job_id, chunk.filename)


def _public_chunk_url(
    request: Request,
    container: Container,
    job_id: str,
    index: int,
    *,
    exp: int,
    sig: str,
) -> str:
    """Абсолютный URL публичной отдачи куска с подписью в query.

    Если задан ``PUBLIC_BASE_URL`` - строим от него (надёжно за TLS-прокси),
    иначе выводим из запроса (учитывает ``root_path``).
    """
    query = f"?exp={exp}&sig={sig}"
    base = container.settings.public_base_url
    if base:
        return f"{base}/api/v1/public/chunks/{job_id}/{index}{query}"
    url = request.url_for("serve_public_chunk", job_id=job_id, index=index)
    return f"{url}{query}"
