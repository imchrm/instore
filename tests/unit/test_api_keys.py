"""Тесты разбора и проверки API-ключей."""

from __future__ import annotations

import pytest

from stories_backend.infrastructure.security.api_keys import ApiKeyRegistry


def test_from_config_parses_pairs() -> None:
    registry = ApiKeyRegistry.from_config("My Phone:secret-1, Tablet:secret-2")

    assert len(registry) == 2
    assert registry.key_id_for("secret-1") == "my_phone"
    assert registry.key_id_for("secret-2") == "tablet"
    assert "secret-1" in registry


def test_unknown_key_returns_none() -> None:
    registry = ApiKeyRegistry.from_config("Phone:secret")

    assert registry.key_id_for("nope") is None


def test_blank_segments_are_ignored() -> None:
    registry = ApiKeyRegistry.from_config(" Phone:secret , , ")

    assert len(registry) == 1
    assert registry.key_id_for("secret") == "phone"


def test_repr_does_not_leak_secrets() -> None:
    registry = ApiKeyRegistry.from_config("Phone:super-secret")

    assert "super-secret" not in repr(registry)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "no-colon-here",
        "Phone:",
        ":secret",
    ],
)
def test_invalid_config_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="API_KEYS"):
        ApiKeyRegistry.from_config(raw)


def test_duplicate_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="дублирующийся ключ"):
        ApiKeyRegistry.from_config("Phone:secret, Tablet:secret")


def test_duplicate_key_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="key_id"):
        ApiKeyRegistry.from_config("My Phone:secret-1, my-phone:secret-2")


def test_name_without_slug_chars_is_rejected() -> None:
    with pytest.raises(ValueError, match="key_id"):
        ApiKeyRegistry.from_config("---:secret")
