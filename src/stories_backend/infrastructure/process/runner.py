"""Абстракция запуска внешних процессов.

Порт ``ProcessRunner`` отделяет медиа-адаптеры от конкретного механизма запуска
подпроцессов, что позволяет подменять его в тестах фейком без реальных
``ffmpeg``/``yt-dlp``. Продакшен-реализация - ``AsyncioProcessRunner``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

# Колбэк построчной обработки stdout (для потокового парсинга прогресса).
LineCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Итог запуска процесса."""

    returncode: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    """Контракт запуска внешнего процесса."""

    async def run(self, argv: Sequence[str]) -> ProcessResult:
        """Запустить процесс и вернуть его результат целиком."""
        ...

    async def run_streaming(
        self, argv: Sequence[str], on_stdout_line: LineCallback
    ) -> ProcessResult:
        """Запустить процесс, отдавая строки stdout в колбэк по мере поступления.

        В возвращаемом ``ProcessResult`` поле ``stdout`` пустое (оно уже
        роздано построчно), ``stderr`` собирается целиком.
        """
        ...


class AsyncioProcessRunner:
    """Реализация ``ProcessRunner`` поверх ``asyncio`` subprocess."""

    async def run(self, argv: Sequence[str]) -> ProcessResult:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        return ProcessResult(
            returncode=process.returncode or 0,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
        )

    async def run_streaming(
        self, argv: Sequence[str], on_stdout_line: LineCallback
    ) -> ProcessResult:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout = process.stdout
        stderr = process.stderr
        if stdout is None or stderr is None:  # pragma: no cover - PIPE всегда задан выше
            msg = "процесс запущен без каналов stdout/stderr"
            raise RuntimeError(msg)

        stderr_chunks: list[bytes] = []
        stderr_task = asyncio.create_task(_drain(stderr, stderr_chunks))
        async for raw_line in stdout:
            await on_stdout_line(raw_line.decode(errors="replace").rstrip("\n"))
        await stderr_task
        returncode = await process.wait()
        return ProcessResult(
            returncode=returncode,
            stdout="",
            stderr=b"".join(stderr_chunks).decode(errors="replace"),
        )


async def _drain(stream: asyncio.StreamReader, sink: list[bytes]) -> None:
    async for line in stream:
        sink.append(line)
