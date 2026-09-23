"""Адаптеры персистентности задач (SQLite)."""

from __future__ import annotations

from .sqlite_repo import SqliteJobRepository

__all__ = ["SqliteJobRepository"]
