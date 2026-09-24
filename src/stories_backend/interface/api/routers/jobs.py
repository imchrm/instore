"""Роутер задач: создание, статус/манифест, удаление, SSE-прогресс, отдача кусков."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from stories_backend.application.use_cases.create_job import CreateJobCommand
from stories_backend.domain.entities import ProgressEvent
from stories_backend.domain.enums import JobStatus
from stories_backend.interface.api.deps import ContainerDep, KeyIdDep
from stories_backend.interface.api.mappers import job_to_response, progress_event_to_dto
from stories_backend.interface.api.schemas import JobCreateRequest, JobResponse

router = APIRouter(prefix="/api/v1", tags=["jobs"])

_CHUNK_MEDIA_TYPE = "video/mp4"
_TERMINAL_STATUSES = frozenset({JobStatus.READY, JobStatus.FAILED, JobStatus.EXPIRED})


def _chunk_url(job_id: str, index: int) -> str:
    return f"/api/v1/jobs/{job_id}/chunks/{index}"


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
    return job_to_response(job, _chunk_url)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, container: ContainerDep, key_id: KeyIdDep) -> JobResponse:
    """Вернуть статус/манифест задачи текущего ключа."""
    job = await container.get_job.execute(job_id, key_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="задача не найдена")
    return job_to_response(job, _chunk_url)


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


@router.get("/jobs/{job_id}/chunks/{index}")
async def get_chunk(job_id: str, index: int, container: ContainerDep, key_id: KeyIdDep) -> Response:
    """Отдать файл куска: через X-Accel-Redirect (prod) или FileResponse (dev)."""
    job = await container.get_job.execute(job_id, key_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="задача не найдена")
    chunk = next((item for item in job.chunks if item.index == index), None)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="кусок не найден")

    settings = container.settings
    if settings.use_xaccel:
        internal = f"{settings.xaccel_internal_prefix}/{job_id}/{chunk.filename}"
        return Response(headers={"X-Accel-Redirect": internal}, media_type=_CHUNK_MEDIA_TYPE)

    path = Path(container.storage.job_dir(job_id)) / chunk.filename
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="файл куска отсутствует")
    return FileResponse(path, media_type=_CHUNK_MEDIA_TYPE)
