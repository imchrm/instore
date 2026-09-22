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
