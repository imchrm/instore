"""Файловое хранилище задач и кусков (реализация ``StoragePort``).

Структура: ``DATA_DIR/jobs/{job_id}/`` с исходником, промежуточным ``conv.mp4``,
кусками ``conv_%03d.mp4`` и ``manifest.json``.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

_INTERMEDIATE_CONV = "conv.mp4"
_SOURCE_GLOB = "source.*"


class FilesystemStorage:
    """Каталоги задач на локальной файловой системе."""

    def __init__(self, data_dir: str | Path) -> None:
        self._jobs_root = Path(data_dir) / "jobs"

    def _job_path(self, job_id: str) -> Path:
        if not job_id or job_id in {".", ".."} or "/" in job_id or "\\" in job_id:
            msg = f"недопустимый job_id: {job_id!r}"
            raise ValueError(msg)
        return self._jobs_root / job_id

    def job_dir(self, job_id: str) -> str:
        """Вернуть путь каталога задачи, создав его при необходимости."""
        path = self._job_path(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    async def remove_job(self, job_id: str) -> None:
        """Удалить каталог задачи целиком."""
        path = self._job_path(job_id)
        await asyncio.to_thread(shutil.rmtree, path, ignore_errors=True)

    async def remove_intermediate(self, job_id: str) -> None:
        """Удалить промежуточные файлы (``source.*`` и ``conv.mp4``), сохранив куски."""
        await asyncio.to_thread(self._remove_intermediate_sync, job_id)

    def _remove_intermediate_sync(self, job_id: str) -> None:
        job_path = self._job_path(job_id)
        if not job_path.is_dir():
            return
        for source in job_path.glob(_SOURCE_GLOB):
            source.unlink(missing_ok=True)
        (job_path / _INTERMEDIATE_CONV).unlink(missing_ok=True)
