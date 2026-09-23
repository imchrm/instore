"""In-process asyncio-очередь и воркер обработки задач.

``JobQueue`` реализует ``JobSubmitterPort``: ``submit`` кладёт ``job_id`` в
очередь, а фоновый потребитель разбирает её, ограничивая параллелизм
семафором (``max_concurrent_jobs``). Обработку одной задачи выполняет
``JobProcessorPort`` (сценарий ``process_job``).
"""

from __future__ import annotations

import asyncio
import contextlib

from stories_backend.application.ports import JobProcessorPort

_DEFAULT_MAX_CONCURRENT = 1


class JobQueue:
    """Очередь задач с фоновым потребителем и ограничением параллелизма."""

    def __init__(
        self,
        processor: JobProcessorPort,
        *,
        max_concurrent_jobs: int = _DEFAULT_MAX_CONCURRENT,
    ) -> None:
        self._processor = processor
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self._consumer: asyncio.Task[None] | None = None
        self._running: set[asyncio.Task[None]] = set()

    async def submit(self, job_id: str) -> None:
        """Поставить задачу в очередь обработки (``JobSubmitterPort``)."""
        await self._queue.put(job_id)

    async def start(self) -> None:
        """Запустить фонового потребителя (идемпотентно)."""
        if self._consumer is None:
            self._consumer = asyncio.create_task(self._consume())

    async def join(self) -> None:
        """Дождаться, пока все поставленные задачи будут обработаны."""
        await self._queue.join()

    async def stop(self) -> None:
        """Остановить потребителя и отменить незавершённые обработки."""
        if self._consumer is not None:
            self._consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer
            self._consumer = None
        for task in list(self._running):
            task.cancel()
        for task in list(self._running):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._running.clear()

    async def _consume(self) -> None:
        while True:
            job_id = await self._queue.get()
            await self._semaphore.acquire()
            task = asyncio.create_task(self._run(job_id))
            self._running.add(task)
            task.add_done_callback(self._running.discard)

    async def _run(self, job_id: str) -> None:
        try:
            await self._processor.execute(job_id)
        finally:
            self._semaphore.release()
            self._queue.task_done()
