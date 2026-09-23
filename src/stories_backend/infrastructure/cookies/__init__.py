"""Адаптеры хранения cookies по key_id."""

from __future__ import annotations

from .filesystem_cookies import FilesystemCookiesStore

__all__ = ["FilesystemCookiesStore"]
