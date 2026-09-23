"""Порты уровня application, дополняющие порты domain.

Здесь живут абстракции, специфичные для сценариев (постановка задачи в очередь,
источники времени и идентификаторов), а не для доменных возможностей.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

# Источник текущего времени (unix-время в секундах) и генератор идентификаторов -
# инъектируются в сценарии для детерминизма в тестах.
Clock = Callable[[], float]
IdGenerator = Callable[[], str]


class JobSubmitterPort(Protocol):
    """Постановка задачи на асинхронную обработку (реализуется воркером)."""

    async def submit(self, job_id: str) -> None: ...


class JobProcessorPort(Protocol):
    """Обработка одной задачи по её идентификатору (реализуется сценарием process_job)."""

    async def execute(self, job_id: str) -> None: ...
