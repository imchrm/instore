"""Роутер администрирования cookies текущего ключа: загрузка, статус, удаление."""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import Response

from stories_backend.interface.api.deps import ContainerDep, KeyIdDep
from stories_backend.interface.api.mappers import cookies_status_to_dto
from stories_backend.interface.api.schemas import CookiesStatusDto

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/cookies", status_code=status.HTTP_204_NO_CONTENT)
async def upload_cookies(request: Request, container: ContainerDep, key_id: KeyIdDep) -> Response:
    """Загрузить cookies.txt для текущего ключа (тело запроса - содержимое файла)."""
    content = await request.body()
    await container.cookies_admin.upload(key_id, content)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/cookies/status", response_model=CookiesStatusDto)
async def cookies_status(container: ContainerDep, key_id: KeyIdDep) -> CookiesStatusDto:
    """Вернуть состояние cookies текущего ключа."""
    return cookies_status_to_dto(await container.cookies_admin.status(key_id))


@router.delete("/cookies", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cookies(container: ContainerDep, key_id: KeyIdDep) -> Response:
    """Удалить cookies текущего ключа."""
    await container.cookies_admin.delete(key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
