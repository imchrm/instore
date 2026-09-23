"""Тесты конфигурации сервиса (Pydantic Settings)."""

from __future__ import annotations

from stories_backend.interface.config import Settings


def test_to_limits_maps_fields() -> None:
    settings = Settings(
        api_keys="phone:secret",
        data_dir="/data",
        max_filesize_mb=42,
        max_video_duration=999,
        job_ttl_seconds=111,
        target_fps=24,
    )

    limits = settings.to_limits()

    assert limits.max_filesize_mb == 42
    assert limits.max_video_duration_sec == 999
    assert limits.job_ttl_seconds == 111
    assert limits.target_fps == 24


def test_resolved_cookies_dir_default() -> None:
    settings = Settings(api_keys="phone:secret", data_dir="/data")

    assert settings.resolved_cookies_dir == "/data/cookies"
    assert settings.db_path == "/data/jobs.sqlite3"


def test_resolved_cookies_dir_explicit() -> None:
    settings = Settings(api_keys="phone:secret", data_dir="/data", cookies_dir="/cookies")

    assert settings.resolved_cookies_dir == "/cookies"
