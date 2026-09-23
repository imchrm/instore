"""Тесты файлового хранилища задач."""

from __future__ import annotations

from pathlib import Path

import pytest

from stories_backend.infrastructure.storage.filesystem_storage import FilesystemStorage


def test_job_dir_creates_directory(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)

    job_dir = Path(storage.job_dir("job-1"))

    assert job_dir.is_dir()
    assert job_dir == tmp_path / "jobs" / "job-1"


async def test_remove_intermediate_keeps_chunks_and_manifest(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)
    job_dir = Path(storage.job_dir("job-1"))
    (job_dir / "source.mp4").write_bytes(b"src")
    (job_dir / "conv.mp4").write_bytes(b"conv")
    (job_dir / "conv_000.mp4").write_bytes(b"chunk-0")
    (job_dir / "manifest.json").write_text("{}", encoding="utf-8")

    await storage.remove_intermediate("job-1")

    assert not (job_dir / "source.mp4").exists()
    assert not (job_dir / "conv.mp4").exists()
    assert (job_dir / "conv_000.mp4").exists()
    assert (job_dir / "manifest.json").exists()


async def test_remove_intermediate_on_missing_job_is_noop(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)

    await storage.remove_intermediate("absent")  # не должно бросать


async def test_remove_job_deletes_directory(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)
    job_dir = Path(storage.job_dir("job-1"))
    (job_dir / "conv_000.mp4").write_bytes(b"chunk-0")

    await storage.remove_job("job-1")

    assert not job_dir.exists()


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b"])
def test_invalid_job_id_is_rejected(tmp_path: Path, bad: str) -> None:
    storage = FilesystemStorage(tmp_path)

    with pytest.raises(ValueError, match="job_id"):
        storage.job_dir(bad)
