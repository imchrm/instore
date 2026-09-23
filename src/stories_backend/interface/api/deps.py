"""Зависимости FastAPI: доступ к контейнеру и аутентификация по ``X-API-Key``."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from stories_backend.interface.api.container import Container


def get_container(request: Request) -> Container:
    """Вернуть DI-контейнер, собранный в lifespan приложения."""
    return cast("Container", request.app.state.container)


async def get_key_id(
    container: Annotated[Container, Depends(get_container)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Проверить ``X-API-Key`` и вернуть стабильный ``key_id`` или бросить 401."""
    key_id = None if x_api_key is None else container.api_keys.key_id_for(x_api_key)
    if key_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="требуется корректный X-API-Key",
        )
    return key_id


ContainerDep = Annotated[Container, Depends(get_container)]
KeyIdDep = Annotated[str, Depends(get_key_id)]
