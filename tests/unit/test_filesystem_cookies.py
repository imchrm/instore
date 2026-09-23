"""Тесты хранилища cookies по key_id."""

from __future__ import annotations

import stat
from pathlib import Path

from stories_backend.infrastructure.cookies.filesystem_cookies import FilesystemCookiesStore


async def test_save_then_path_and_permissions(tmp_path: Path) -> None:
    store = FilesystemCookiesStore(tmp_path)

    await store.save("phone", b"cookie-content")

    saved = await store.path("phone")
    assert saved is not None
    saved_path = Path(saved)
    assert saved_path.read_bytes() == b"cookie-content"
    mode = stat.S_IMODE(saved_path.stat().st_mode)
    assert mode == 0o600


async def test_path_absent_returns_none(tmp_path: Path) -> None:
    store = FilesystemCookiesStore(tmp_path)

    assert await store.path("phone") is None


async def test_status_absent_and_present(tmp_path: Path) -> None:
    store = FilesystemCookiesStore(tmp_path)

    absent = await store.status("phone")
    assert absent.present is False
    assert absent.uploaded_at is None

    await store.save("phone", b"data")
    present = await store.status("phone")
    assert present.present is True
    assert present.uploaded_at is not None
    assert present.likely_expired is False


async def test_status_marks_old_cookies_expired(tmp_path: Path) -> None:
    store = FilesystemCookiesStore(tmp_path, likely_expired_seconds=0)

    await store.save("phone", b"data")
    status = await store.status("phone")

    assert status.present is True
    assert status.likely_expired is True


async def test_overwrite_and_delete(tmp_path: Path) -> None:
    store = FilesystemCookiesStore(tmp_path)

    await store.save("phone", b"first")
    await store.save("phone", b"second")
    saved = await store.path("phone")
    assert saved is not None
    assert Path(saved).read_bytes() == b"second"

    await store.delete("phone")
    assert await store.path("phone") is None
    await store.delete("phone")  # повторное удаление не бросает
