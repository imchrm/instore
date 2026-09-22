"""Smoke-тест каркаса: пакет импортируется и объявляет версию."""

from __future__ import annotations

import stories_backend


def test_version_is_exposed() -> None:
    assert isinstance(stories_backend.__version__, str)
    assert stories_backend.__version__
