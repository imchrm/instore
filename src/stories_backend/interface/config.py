"""Конфигурация сервиса из окружения (Pydantic Settings).

Значения читаются из переменных окружения (и опционального ``.env``) по таблице
ENV из ``docs/ARCHITECTURE.md``. Метод :meth:`Settings.to_limits` отдаёт
доменные лимиты (:class:`ProcessingLimits`), не завязывая application на Pydantic.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from stories_backend.application.config import ProcessingLimits

# Пресеты libx264 от самого быстрого к самому медленному (качество/битрейт растут).
_X264_PRESETS: frozenset[str] = frozenset(
    {
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
        "placebo",
    }
)


class Settings(BaseSettings):
    """Настройки сервиса. Имена полей сопоставляются с ENV без учёта регистра."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_keys: str = Field(description="пары 'имя:ключ' через запятую")
    root_path: str = Field(
        default="",
        description="публичный префикс пути за reverse-proxy (например '/instore'); пусто = корень",
    )
    data_dir: str = "/data"
    cookies_dir: str | None = None
    job_ttl_seconds: int = 1200
    max_concurrent_jobs: int = 1
    max_filesize_mb: int = 50
    max_video_duration: int = 1800
    max_height_default: int = 1080
    segment_time_default: int = 45
    keyframe_limit_sec: int = 60
    target_fps: int = 30
    transcode_preset: str = Field(
        default="veryfast",
        description="пресет libx264 (компромисс скорость/битрейт), напр. veryfast/fast/medium",
    )
    story_max_filesize_mb: int = 30
    signing_secret: str = Field(
        default="",
        description="секрет HMAC для подписанных публичных URL кусков; пусто = функция выключена",
    )
    signed_url_ttl_sec: int = 300
    public_base_url: str = Field(
        default="",
        description="база подписанных URL (напр. https://host/instore); пусто = вывести из запроса",
    )
    cleanup_interval_sec: int = 60
    use_xaccel: bool = False
    xaccel_internal_prefix: str = "/_protected"
    log_level: str = "INFO"

    @field_validator("root_path")
    @classmethod
    def _normalize_root_path(cls, value: str) -> str:
        """Нормализовать префикс: без концевого '/', с ведущим '/' (или пусто для корня)."""
        trimmed = value.strip().strip("/")
        return f"/{trimmed}" if trimmed else ""

    @field_validator("public_base_url")
    @classmethod
    def _normalize_public_base_url(cls, value: str) -> str:
        """Срезать концевой '/' (путь подписанной ссылки добавляется явно)."""
        return value.strip().rstrip("/")

    @field_validator("transcode_preset")
    @classmethod
    def _validate_preset(cls, value: str) -> str:
        """Разрешить только валидные пресеты libx264 (иначе ffmpeg упадёт на каждой задаче)."""
        normalized = value.strip().lower()
        if normalized not in _X264_PRESETS:
            allowed = ", ".join(_X264_PRESETS)
            msg = f"недопустимый TRANSCODE_PRESET '{value}'; допустимы: {allowed}"
            raise ValueError(msg)
        return normalized

    @property
    def resolved_cookies_dir(self) -> str:
        """Каталог cookies: ``COOKIES_DIR`` или ``${DATA_DIR}/cookies`` по умолчанию."""
        if self.cookies_dir is not None:
            return self.cookies_dir
        return str(Path(self.data_dir) / "cookies")

    @property
    def db_path(self) -> str:
        """Путь к файлу SQLite с задачами."""
        return str(Path(self.data_dir) / "jobs.sqlite3")

    def to_limits(self) -> ProcessingLimits:
        """Собрать доменные лимиты конвейера из настроек."""
        return ProcessingLimits(
            max_filesize_mb=self.max_filesize_mb,
            max_video_duration_sec=self.max_video_duration,
            max_height_default=self.max_height_default,
            segment_time_default=self.segment_time_default,
            keyframe_limit_sec=self.keyframe_limit_sec,
            target_fps=self.target_fps,
            job_ttl_seconds=self.job_ttl_seconds,
            cleanup_interval_sec=self.cleanup_interval_sec,
            story_max_filesize_mb=self.story_max_filesize_mb,
        )
