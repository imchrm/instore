"""Адаптеры шины событий прогресса (SSE)."""

from __future__ import annotations

from .sse_bus import InProcessEventBus, Subscription

__all__ = ["InProcessEventBus", "Subscription"]
