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


def _client_settings(tmp_path: Path, *, root_path: str = "") -> Settings:
    client_dir = tmp_path / "client"
    (client_dir / "assets").mkdir(parents=True)
    (client_dir / "index.html").write_text("<h1>Mini App</h1>", encoding="utf-8")
    (client_dir / "assets" / "app.js").write_text("export const x = 1;", encoding="utf-8")
    return Settings(
        api_keys="phone:secret",
        data_dir=str(tmp_path),
        client_dir=str(client_dir),
        root_path=root_path,
    )


def test_client_static_served_when_dir_present(tmp_path: Path) -> None:
    with TestClient(create_app(_client_settings(tmp_path))) as client:
        root = client.get("/app/")
        asset = client.get("/app/assets/app.js")

    assert root.status_code == 200
    assert "Mini App" in root.text
    assert asset.status_code == 200
    assert "export const x" in asset.text


def test_client_static_served_behind_root_path(tmp_path: Path) -> None:
    # Регрессия: за reverse-proxy с ROOT_PATH nginx отдаёт срезанный путь /app/.
    # Через StaticFiles-mount это не работало; обычные маршруты - работают.
    with TestClient(create_app(_client_settings(tmp_path, root_path="/instore"))) as client:
        root = client.get("/app/")
        asset = client.get("/app/assets/app.js")

    assert root.status_code == 200
    assert "Mini App" in root.text
    assert asset.status_code == 200


def test_client_static_spa_fallback_to_index(tmp_path: Path) -> None:
    with TestClient(create_app(_client_settings(tmp_path))) as client:
        response = client.get("/app/unknown/route")

    assert response.status_code == 200
    assert "Mini App" in response.text


def test_client_static_absent_without_dir(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get("/app/")

    assert response.status_code == 404
