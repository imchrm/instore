"""Лимиты и дефолты обработки, от которых зависят сценарии application.

Значения соответствуют таблице ENV из ``docs/ARCHITECTURE.md``. Слой interface
(Фаза 5) наполняет этот объект из Pydantic Settings; сам application от Pydantic
не зависит.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessingLimits:
    """Границы и дефолты конвейера обработки."""

    max_filesize_mb: int = 50
    max_video_duration_sec: int = 1800
    max_height_default: int = 1080
    segment_time_default: int = 45
    keyframe_limit_sec: int = 60
    target_fps: int = 30
    job_ttl_seconds: int = 1200
    cleanup_interval_sec: int = 60
