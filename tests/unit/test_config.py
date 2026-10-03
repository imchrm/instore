"""Тесты конфигурации сервиса (Pydantic Settings)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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


def test_root_path_default_is_empty() -> None:
    settings = Settings(api_keys="phone:secret")

    assert settings.root_path == ""


def test_root_path_normalized() -> None:
    for raw, expected in [
        ("instore", "/instore"),
        ("/instore", "/instore"),
        ("/instore/", "/instore"),
        ("  /instore/  ", "/instore"),
        ("instore/api", "/instore/api"),
        ("/", ""),
        ("", ""),
    ]:
        settings = Settings(api_keys="phone:secret", root_path=raw)
        assert settings.root_path == expected, raw


def test_transcode_preset_default() -> None:
    settings = Settings(api_keys="phone:secret")

    assert settings.transcode_preset == "veryfast"


def test_transcode_preset_normalized() -> None:
    settings = Settings(api_keys="phone:secret", transcode_preset="  FAST  ")

    assert settings.transcode_preset == "fast"


def test_transcode_preset_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        Settings(api_keys="phone:secret", transcode_preset="turbo")


def test_signed_url_defaults() -> None:
    settings = Settings(api_keys="phone:secret")

    assert settings.signing_secret == ""
    assert settings.signed_url_ttl_sec == 300
    assert settings.public_base_url == ""
    assert settings.story_max_filesize_mb == 30
    assert settings.to_limits().story_max_filesize_mb == 30


def test_public_base_url_strips_trailing_slash() -> None:
    settings = Settings(api_keys="phone:secret", public_base_url="https://host/instore/")

    assert settings.public_base_url == "https://host/instore"
