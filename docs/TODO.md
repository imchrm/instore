# TODO — stories-backend

План работ по серверной части. Разбит на фазы; внутри фазы порядок примерный.
Легенда: `[ ]` не начато, `[~]` в работе, `[x]` готово.

## Фаза 0. Каркас проекта

- [x] Инициализация репозитория, структура каталогов по `ARCHITECTURE.md`
- [x] `pyproject.toml`: Python 3.12+, зависимости (fastapi, uvicorn, pydantic v2, pydantic-settings, aiosqlite, structlog/loguru)
- [x] Настройка `ruff` (lint + format) и `mypy --strict`
- [x] Базовый `pytest` и CI-гейт (ruff + mypy + pytest)
- [x] Заготовка Dockerfile (multi-stage) с ffmpeg/ffprobe/yt-dlp

## Фаза 1. Domain

- [x] `enums.py`: `JobStatus`, `StoriesFit`, `ErrorCode`
- [x] `entities.py`: `Job`, `Chunk`, `VideoMeta`
- [x] `errors.py`: доменные исключения с привязкой к `ErrorCode`
- [x] `ports.py`: все Protocol-порты (без порта публикации в Stories)
- [x] Unit-тесты валидности переходов автомата статусов

## Фаза 2. Infrastructure — адаптеры

- [x] `persistence/sqlite_repo.py`: `JobRepositoryPort` на aiosqlite, миграция схемы при старте
- [x] `storage/filesystem_storage.py`: каталоги задач, удаление промежуточных и всей задачи
- [x] `events/sse_bus.py`: `EventBusPort` (подписка/публикация на процесс)
- [x] `downloader/ytdlp.py`: `probe_meta` и `download` с ограничениями (`--max-filesize`, высота, cookies), парсинг progress-hooks, маппинг ошибок yt-dlp в `ErrorCode`
- [x] `media/ffmpeg_transcoder.py`: transcode c `force_key_frames` и фильтрами `stories_fit`, парсинг `-progress pipe:1`
- [x] `media/ffmpeg_segmenter.py`: нарезка `-c copy -f segment`
- [x] `media/ffprobe_probe.py`: длительность куска
- [x] `cookies/filesystem_cookies.py`: хранение по `key_id`, атомарная запись, права 0600, статус/удаление
- [x] `security/api_keys.py`: парсинг `API_KEYS` в `key -> key_id`, проверка ключа

## Фаза 3. Application — сценарии

- [ ] `create_job`: валидация, регистрация задачи, постановка в очередь
- [ ] `process_job` + `services/job_processing.py`: оркестрация конвейера (download → transcode → segment → probe → ready), обновление прогресса и статусов
- [ ] `get_job`: чтение с проверкой `key_id`
- [ ] `stream_progress`: поток SSE по задаче
- [ ] `delete_job`: удаление задачи и файлов с проверкой `key_id`
- [ ] `cleanup_expired`: перевод `ready` в `expired` по TTL и удаление файлов
- [ ] `cookies_admin`: upload/status/delete cookies для текущего `key_id`
- [ ] Unit-тесты сценариев на fake-портах (включая `TOO_LARGE`, `AUTH_REQUIRED`, изоляцию по `key_id`)

## Фаза 4. Worker

- [ ] `worker/queue.py`: asyncio-очередь и воркер, семафор `MAX_CONCURRENT_JOBS`
- [ ] Пометка прерванных рестартом задач как `failed (INTERNAL)` при старте
- [ ] `worker/scheduler.py`: периодическая очистка по `CLEANUP_INTERVAL_SEC`

## Фаза 5. Interface — API

- [ ] `interface/config.py`: Pydantic Settings по таблице ENV
- [ ] `interface/api/app.py`: сборка FastAPI, lifespan (запуск воркера и планировщика), DI-граф
- [ ] `deps.py`: аутентификация `X-API-Key`, извлечение `key_id`
- [ ] `schemas.py` + `mappers.py`: DTO и маппинг domain <-> DTO
- [ ] `routers/jobs.py`: POST/GET/DELETE, SSE, отдача кусков (X-Accel-Redirect / FileResponse)
- [ ] `routers/admin.py`: cookies upload/status/delete
- [ ] `routers/system.py`: `/config`, `/health`

## Фаза 6. Тестирование и качество

- [ ] Integration-тест конвейера на коротком тестовом mp4 (fixture)
- [ ] Contract-тест OpenAPI/DTO
- [ ] Проверка: все куски ≤ `KEYFRAME_LIMIT_SEC` при корректных кейфреймах
- [ ] Прогон `ruff` + `mypy --strict` + `pytest` без ошибок

## Фаза 7. Деплой

- [ ] Финализация Dockerfile и docker-compose (сервис + том `DATA_DIR`)
- [ ] Конфиг nginx: проксирование API + internal-локация для X-Accel-Redirect
- [ ] Механизм обновления `yt-dlp` (пересборка по расписанию или шаг при старте)
- [ ] Прогон end-to-end на реальном URL (YouTube и Instagram с cookies)

## Открытые вопросы (вести по мере появления)

- [ ] Значение `MAX_VIDEO_DURATION` подтвердить на практике (сейчас 1800 сек, но при лимите 50 МБ фактически ограничивает размер)
- [ ] Ротация/размер логов
