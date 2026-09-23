# CHANGELOG — stories-backend

Все значимые изменения серверной части фиксируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект придерживается [семантического версионирования](https://semver.org/lang/ru/).

## [Unreleased]

### Added

- Проектная документация: `CONTEXT.md`, `ARCHITECTURE.md`, `TODO.md`, `CHANGELOG.md`.
- Согласована архитектура серверной части (Clean Architecture / DDD): слои domain / application / infrastructure / interface.
- Определён контракт REST/SSE API: создание задачи, статус/манифест, поток прогресса, отдача кусков, админ-эндпоинты cookies, `/config`, `/health`.
- Определён конвейер обработки: download (yt-dlp) → transcode (ffmpeg, force_key_frames, режимы `stories_fit`) → segment (`-c copy`) → probe (ffprobe) → ready.
- Определён автомат состояний задачи и таксономия ошибок.
- Каркас проекта (Фаза 0): `pyproject.toml` (hatchling, src-layout, Python 3.12+), конфигурация `ruff` (lint + format) и `mypy --strict`, `pytest`.
- Пакет `stories_backend` с маркером `py.typed` (PEP 561) и скелетом каталогов слоёв (domain / application / infrastructure / interface / worker).
- CI-гейт GitHub Actions: `ruff` + `mypy --strict` + `pytest`.
- Заготовка `Dockerfile` (multi-stage) с ffmpeg/ffprobe и yt-dlp.
- Слой domain (Фаза 1): `enums.py` (`JobStatus`, `StoriesFit`, `ErrorCode`), `entities.py` (`Job`, `Chunk`, `VideoMeta`, `ProgressEvent`, `CookiesStatus`), автомат переходов статусов (`can_transition`, `Job.transition_to`, `Job.mark_failed`).
- `errors.py`: доменные исключения с привязкой к `ErrorCode` и функция `error_for_code`.
- `ports.py`: Protocol-порты (downloader, transcoder, segmenter, probe, repository, event bus, storage, cookies) и тип `ProgressCallback`; порт публикации в Stories осознанно отсутствует.
- Unit-тесты автомата состояний и доменных ошибок.

### Decided

- Очередь и хранение: in-process asyncio-воркер + SQLite; без arq/Redis.
- Лимит исходного видео `MAX_FILESIZE_MB = 50` с проверкой по метаданным и через `--max-filesize`.
- Ограничение высоты по умолчанию 1080p.
- TTL готовых кусков 1200 секунд; промежуточные файлы удаляются сразу после `probe`.
- Нарезка по 45 секунд с гарантией границ через принудительные кейфреймы на шаге transcode.
- Приведение под Stories параметром `stories_fit: none | cover | pad` (по умолчанию `none`).
- Аутентификация по `X-API-Key`; несколько ключей (пары `имя:ключ`).
- Изоляция задач по `key_id`.
- Instagram cookies хранятся по `key_id`; общий fallback-файл не используется; загрузка вне основного потока, использование по флагу `use_cookies`.

### Out of scope

- Автоматическая публикация в Telegram Stories (userbot/MTProto) исключена; порт публикации не закладывается.

[Unreleased]: about:blank
