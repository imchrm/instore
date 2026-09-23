"""Тесты внутрипроцессной шины событий прогресса."""

from __future__ import annotations

from stories_backend.domain.entities import ProgressEvent
from stories_backend.domain.enums import JobStatus
from stories_backend.infrastructure.events.sse_bus import InProcessEventBus


def make_event(job_id: str, progress: float) -> ProgressEvent:
    return ProgressEvent(job_id=job_id, status=JobStatus.DOWNLOADING, phase_progress=progress)


async def test_subscriber_receives_published_event() -> None:
    bus = InProcessEventBus()
    stream = bus.subscribe("job-1")

    event = make_event("job-1", 0.5)
    await bus.publish("job-1", event)

    received = await anext(stream)
    assert received == event
    await stream.aclose()


async def test_events_are_buffered_in_order() -> None:
    bus = InProcessEventBus()
    stream = bus.subscribe("job-1")

    await bus.publish("job-1", make_event("job-1", 0.1))
    await bus.publish("job-1", make_event("job-1", 0.2))

    first = await anext(stream)
    second = await anext(stream)
    assert (first.phase_progress, second.phase_progress) == (0.1, 0.2)
    await stream.aclose()


async def test_multiple_subscribers_receive_same_event() -> None:
    bus = InProcessEventBus()
    first = bus.subscribe("job-1")
    second = bus.subscribe("job-1")

    event = make_event("job-1", 0.1)
    await bus.publish("job-1", event)

    assert await anext(first) == event
    assert await anext(second) == event
    await first.aclose()
    await second.aclose()


async def test_publish_without_subscribers_is_noop() -> None:
    bus = InProcessEventBus()

    await bus.publish("job-1", make_event("job-1", 0.9))  # не должно бросать


async def test_subscriber_is_removed_after_close() -> None:
    bus = InProcessEventBus()
    stream = bus.subscribe("job-1")
    await stream.aclose()

    await bus.publish("job-1", make_event("job-1", 1.0))
    assert bus._subscribers == {}
