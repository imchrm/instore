"""Хранение cookies по ``key_id`` (реализация ``CookiesStorePort``).

Файлы лежат в ``COOKIES_DIR/{key_id}.txt`` с правами ``0600`` и записываются
атомарно (временный файл + ``os.replace``). Общий fallback-файл не используется.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from stories_backend.domain.entities import CookiesStatus

# Возраст cookies, после которого они считаются вероятно протухшими.
_DEFAULT_LIKELY_EXPIRED_SECONDS = 30 * 24 * 3600
_FILE_MODE = 0o600


class FilesystemCookiesStore:
    """Cookies на локальной файловой системе, по одному файлу на ``key_id``."""

    def __init__(
        self,
        cookies_dir: str | Path,
        *,
        likely_expired_seconds: float = _DEFAULT_LIKELY_EXPIRED_SECONDS,
    ) -> None:
        self._dir = Path(cookies_dir)
        self._likely_expired_seconds = likely_expired_seconds

    def _path(self, key_id: str) -> Path:
        if not key_id or key_id in {".", ".."} or "/" in key_id or "\\" in key_id:
            msg = f"недопустимый key_id: {key_id!r}"
            raise ValueError(msg)
        return self._dir / f"{key_id}.txt"

    async def save(self, key_id: str, content: bytes) -> None:
        """Атомарно сохранить содержимое cookies с правами ``0600``."""
        await asyncio.to_thread(self._save_sync, key_id, content)

    def _save_sync(self, key_id: str, content: bytes) -> None:
        target = self._path(key_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        os.chmod(tmp, _FILE_MODE)
        os.replace(tmp, target)
        os.chmod(target, _FILE_MODE)

    async def path(self, key_id: str) -> str | None:
        """Вернуть путь к файлу cookies или ``None``, если его нет."""
        candidate = self._path(key_id)
        exists = await asyncio.to_thread(candidate.is_file)
        return str(candidate) if exists else None

    async def status(self, key_id: str) -> CookiesStatus:
        """Вернуть состояние cookies: наличие, время загрузки и признак протухания."""
        return await asyncio.to_thread(self._status_sync, key_id)

    def _status_sync(self, key_id: str) -> CookiesStatus:
        candidate = self._path(key_id)
        if not candidate.is_file():
            return CookiesStatus(present=False)
        uploaded_at = candidate.stat().st_mtime
        likely_expired = (time.time() - uploaded_at) > self._likely_expired_seconds
        return CookiesStatus(present=True, uploaded_at=uploaded_at, likely_expired=likely_expired)

    async def delete(self, key_id: str) -> None:
        """Удалить файл cookies, если он существует."""
        await asyncio.to_thread(self._delete_sync, key_id)

    def _delete_sync(self, key_id: str) -> None:
        self._path(key_id).unlink(missing_ok=True)
