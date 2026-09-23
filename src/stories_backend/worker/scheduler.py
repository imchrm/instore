"""Периодический планировщик очистки просроченных задач.

Раз в ``interval_sec`` вызывает ``CleanupExpiredUseCase``. Один тик доступен
отдельно (``run_once``) для тестов и ручного запуска.
"""

from __future__ import annotations

import asyncio
import contextlib

from stories_backend.application.use_cases.cleanup_expired import CleanupExpiredUseCase


class PeriodicCleanupScheduler:
    """Фоновый таск, периодически запускающий очистку по TTL."""

    def __init__(self, cleanup: CleanupExpiredUseCase, *, interval_sec: float) -> None:
        self._cleanup = cleanup
        self._interval_sec = interval_sec
        self._task: asyncio.Task[None] | None = None

    async def run_once(self) -> list[str]:
        """Выполнить один проход очистки и вернуть id очищенных задач."""
        return await self._cleanup.execute()

    async def start(self) -> None:
        """Запустить периодический цикл (идемпотентно)."""
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Остановить периодический цикл."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval_sec)
            # Сбой одного прохода не должен ронять планировщик.
            with contextlib.suppress(Exception):
                await self.run_once()
