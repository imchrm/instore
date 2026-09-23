"""Запуск внешних процессов: инъектируемый раннер поверх asyncio subprocess."""

from __future__ import annotations

from .runner import AsyncioProcessRunner, LineCallback, ProcessResult, ProcessRunner

__all__ = ["AsyncioProcessRunner", "LineCallback", "ProcessResult", "ProcessRunner"]
