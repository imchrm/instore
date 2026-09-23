"""Статическая проверка соответствия адаптеров портам домена.

Модуль не содержит тестов и не исполняется в рантайме: он существует только
для ``mypy`` (проверка выполняется в блоке ``TYPE_CHECKING``). Имя с префиксом
``_`` исключает его из сбора pytest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import cast

    import aiosqlite

    from stories_backend.domain.ports import (
        CookiesStorePort,
        EventBusPort,
        JobRepositoryPort,
        StoragePort,
    )
    from stories_backend.infrastructure.cookies.filesystem_cookies import FilesystemCookiesStore
    from stories_backend.infrastructure.events.sse_bus import InProcessEventBus
    from stories_backend.infrastructure.persistence.sqlite_repo import SqliteJobRepository
    from stories_backend.infrastructure.storage.filesystem_storage import FilesystemStorage

    _storage: StoragePort = FilesystemStorage("/tmp/data")
    _cookies: CookiesStorePort = FilesystemCookiesStore("/tmp/cookies")
    _bus: EventBusPort = InProcessEventBus()
    _repo: JobRepositoryPort = SqliteJobRepository(cast("aiosqlite.Connection", None))
