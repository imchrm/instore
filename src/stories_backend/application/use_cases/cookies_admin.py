"""Админ-сценарии cookies для текущего ``key_id``: загрузка, статус, удаление."""

from __future__ import annotations

from stories_backend.domain.entities import CookiesStatus
from stories_backend.domain.ports import CookiesStorePort


class CookiesAdminUseCase:
    """Управление cookies, привязанными к ``key_id``."""

    def __init__(self, cookies_store: CookiesStorePort) -> None:
        self._cookies_store = cookies_store

    async def upload(self, key_id: str, content: bytes) -> None:
        await self._cookies_store.save(key_id, content)

    async def status(self, key_id: str) -> CookiesStatus:
        return await self._cookies_store.status(key_id)

    async def delete(self, key_id: str) -> None:
        await self._cookies_store.delete(key_id)
