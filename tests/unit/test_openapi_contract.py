"""Контракт-тесты OpenAPI-схемы и DTO.

Фиксируют публичный контракт API (набор путей, методов и компонентов-схем),
чтобы случайное изменение маршрутов или DTO ломало сборку осознанно, а не
молча меняло совместимость с мобильным клиентом.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from stories_backend.interface.api.app import create_app
from stories_backend.interface.config import Settings

# Ожидаемый контракт: путь -> множество HTTP-методов.
_EXPECTED_PATHS: dict[str, set[str]] = {
    "/api/v1/health": {"get"},
    "/api/v1/config": {"get"},
    "/api/v1/jobs": {"post"},
    "/api/v1/jobs/{job_id}": {"get", "delete"},
    "/api/v1/jobs/{job_id}/events": {"get"},
    "/api/v1/jobs/{job_id}/chunks/{index}": {"get"},
    "/api/v1/admin/cookies": {"post", "delete"},
    "/api/v1/admin/cookies/status": {"get"},
}

# DTO и доменные перечисления, публикуемые в компонентах схемы.
_EXPECTED_COMPONENTS: set[str] = {
    "JobCreateRequest",
    "JobResponse",
    "ChunkInfo",
    "ErrorInfo",
    "CookiesStatusDto",
    "ServiceConfigDto",
    "JobStatus",
    "StoriesFit",
    "ErrorCode",
}


@pytest.fixture
def openapi_schema(tmp_path: Path) -> dict[str, Any]:
    """OpenAPI-схема приложения (без запуска жизненного цикла и воркера)."""
    settings = Settings(api_keys="Phone:secret", data_dir=str(tmp_path))
    app = create_app(settings)
    return app.openapi()


def test_service_title(openapi_schema: dict[str, Any]) -> None:
    assert openapi_schema["info"]["title"] == "stories-backend"


def test_all_expected_paths_and_methods_present(openapi_schema: dict[str, Any]) -> None:
    paths: dict[str, dict[str, Any]] = openapi_schema["paths"]
    for path, methods in _EXPECTED_PATHS.items():
        assert path in paths, f"отсутствует путь {path}"
        declared = {method.lower() for method in paths[path]}
        assert methods <= declared, f"на {path} не хватает методов {methods - declared}"


def test_no_unexpected_paths(openapi_schema: dict[str, Any]) -> None:
    assert set(openapi_schema["paths"]) == set(_EXPECTED_PATHS)


def test_expected_components_present(openapi_schema: dict[str, Any]) -> None:
    components = openapi_schema["components"]["schemas"]
    missing = _EXPECTED_COMPONENTS - set(components)
    assert not missing, f"в компонентах отсутствуют схемы: {sorted(missing)}"


def test_create_job_request_and_response_contract(openapi_schema: dict[str, Any]) -> None:
    post = openapi_schema["paths"]["/api/v1/jobs"]["post"]
    request_ref = post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref.endswith("/JobCreateRequest")
    response_ref = post["responses"]["202"]["content"]["application/json"]["schema"]["$ref"]
    assert response_ref.endswith("/JobResponse")


def test_config_response_contract(openapi_schema: dict[str, Any]) -> None:
    get = openapi_schema["paths"]["/api/v1/config"]["get"]
    response_ref = get["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert response_ref.endswith("/ServiceConfigDto")


def test_job_create_request_fields_and_bounds(openapi_schema: dict[str, Any]) -> None:
    schema = openapi_schema["components"]["schemas"]["JobCreateRequest"]
    properties: dict[str, Any] = schema["properties"]
    assert set(properties) == {
        "url",
        "segment_time",
        "max_height",
        "stories_fit",
        "use_cookies",
    }
    assert properties["segment_time"]["minimum"] == 5
    assert properties["segment_time"]["maximum"] == 60
    assert properties["max_height"]["minimum"] == 240
    assert properties["max_height"]["maximum"] == 2160
    # url обязателен, остальные поля имеют значения по умолчанию.
    assert schema["required"] == ["url"]
