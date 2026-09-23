"""Внутрипроцессная шина событий прогресса (реализация ``EventBusPort``).

Подписка регистрирует очередь сразу при вызове ``subscribe`` (не лениво), поэтому
события, опубликованные после подписки, буферизуются и не теряются. Шина
рассчитана на один процесс (in-process asyncio-воркер), внешний брокер не нужен.
"""

from __future__ import annotations

import asyncio

from stories_backend.domain.entities import ProgressEvent

_DEFAULT_QUEUE_SIZE = 100


class Subscription:
    """Асинхронный итератор поверх очереди одного подписчика."""

    def __init__(
        self,
        bus: InProcessEventBus,
        job_id: str,
        queue: asyncio.Queue[ProgressEvent],
    ) -> None:
        self._bus = bus
        self._job_id = job_id
        self._queue = queue

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> ProgressEvent:
        return await self._queue.get()

    async def aclose(self) -> None:
        """Отписаться: снять очередь с шины."""
        self._bus.unsubscribe(self._job_id, self._queue)


class InProcessEventBus:
    """Публикация/подписка на события прогресса в пределах процесса."""

    def __init__(self, *, max_queue_size: int = _DEFAULT_QUEUE_SIZE) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[ProgressEvent]]] = {}
        self._max_queue_size = max_queue_size

    async def publish(self, job_id: str, event: ProgressEvent) -> None:
        """Разослать событие всем подписчикам задачи.

        Переполненная очередь медленного подписчика пропускается, чтобы
        публикация не блокировала обработку.
        """
        for queue in list(self._subscribers.get(job_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue

    def subscribe(self, job_id: str) -> Subscription:
        """Подписаться на поток событий задачи (очередь регистрируется сразу)."""
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue(self._max_queue_size)
        self._subscribers.setdefault(job_id, set()).add(queue)
        return Subscription(self, job_id, queue)

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[ProgressEvent]) -> None:
        """Снять очередь подписчика; пустой набор по задаче удаляется."""
        subscribers = self._subscribers.get(job_id)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(job_id, None)
