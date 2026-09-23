"""Системные эндпоинты: ``/health`` и ``/config`` (без аутентификации)."""

from __future__ import annotations

from fastapi import APIRouter

from stories_backend.interface.api.deps import ContainerDep
from stories_backend.interface.api.mappers import limits_to_service_config
from stories_backend.interface.api.schemas import ServiceConfigDto

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Простой признак живости сервиса."""
    return {"status": "ok"}


@router.get("/config", response_model=ServiceConfigDto)
async def get_config(container: ContainerDep) -> ServiceConfigDto:
    """Опубликовать лимиты и дефолты, чтобы клиент показал их до отправки задачи."""
    return limits_to_service_config(container.limits)
