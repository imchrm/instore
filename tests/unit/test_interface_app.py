"""Тесты сборки приложения: жизненный цикл, /health и /config."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from stories_backend.interface.api.app import create_app
from stories_backend.interface.config import Settings


def make_settings(tmp_path: Path) -> Settings:
    return Settings(api_keys="phone:secret", data_dir=str(tmp_path))


def test_health_returns_ok(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_publishes_limits(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get("/api/v1/config")

    assert response.status_code == 200
    body = response.json()
    assert body["max_filesize_mb"] == 50
    assert body["segment_time_default"] == 45
    assert body["stories_fit_options"] == ["none", "cover", "pad"]


def test_lifespan_creates_database(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))):
        pass

    assert (tmp_path / "jobs.sqlite3").exists()


def test_root_path_default_empty(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))

    assert app.root_path == ""


def test_root_path_propagated_to_app(tmp_path: Path) -> None:
    settings = Settings(api_keys="phone:secret", data_dir=str(tmp_path), root_path="/instore")
    app = create_app(settings)

    assert app.root_path == "/instore"
