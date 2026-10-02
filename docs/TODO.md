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

- [x] `create_job`: валидация, регистрация задачи, постановка в очередь
- [x] `process_job` + `services/job_processing.py`: оркестрация конвейера (download → transcode → segment → probe → ready), обновление прогресса и статусов
- [x] `get_job`: чтение с проверкой `key_id`
- [x] `stream_progress`: поток SSE по задаче
- [x] `delete_job`: удаление задачи и файлов с проверкой `key_id`
- [x] `cleanup_expired`: перевод `ready` в `expired` по TTL и удаление файлов
- [x] `cookies_admin`: upload/status/delete cookies для текущего `key_id`
- [x] Unit-тесты сценариев на fake-портах (включая `TOO_LARGE`, `TOO_LONG`, `AUTH_REQUIRED`, изоляцию по `key_id`)

## Фаза 4. Worker

- [x] `worker/queue.py`: asyncio-очередь и воркер, семафор `MAX_CONCURRENT_JOBS`
- [x] Пометка прерванных рестартом задач как `failed (INTERNAL)` при старте
- [x] `worker/scheduler.py`: периодическая очистка по `CLEANUP_INTERVAL_SEC`

## Фаза 5. Interface — API

- [x] `interface/config.py`: Pydantic Settings по таблице ENV
- [x] `interface/api/app.py`: сборка FastAPI, lifespan (запуск воркера и планировщика), DI-граф
- [x] `deps.py`: аутентификация `X-API-Key`, извлечение `key_id`
- [x] `schemas.py` + `mappers.py`: DTO и маппинг domain <-> DTO
- [x] `routers/jobs.py`: POST/GET/DELETE, SSE, отдача кусков (X-Accel-Redirect / FileResponse)
- [x] `routers/admin.py`: cookies upload/status/delete
- [x] `routers/system.py`: `/config`, `/health`

## Фаза 6. Тестирование и качество

- [x] Integration-тест конвейера на коротком тестовом mp4 (fixture генерируется ffmpeg)
- [x] Contract-тест OpenAPI/DTO (набор путей/методов и компонентов-схем)
- [x] Проверка: все куски ≤ `KEYFRAME_LIMIT_SEC` при корректных кейфреймах
      (integration-тест выявил дефект нарезки на границе кейфрейма - исправлено
      через `-segment_time_delta`)
- [x] Прогон `ruff` + `mypy --strict` + `pytest` без ошибок
- [x] ffmpeg в CI (шаг установки перед тестами)

## Фаза 7. Деплой

Исходно область ограничивалась Docker-образом; по ходу эксплуатации добавлены
`docker-compose.yml` и конфигурация nginx (reverse-proxy по подпути `/instore`).

- [x] Финализация Dockerfile (том `DATA_DIR`, непривилегированный пользователь, HEALTHCHECK, entrypoint)
- [x] `.dockerignore` (минимальный контекст сборки: `pyproject.toml`, `src`, entrypoint)
- [x] Механизм обновления `yt-dlp` (пересборка образа или шаг при старте по `YT_DLP_AUTO_UPDATE`)
- [x] Инструкция по деплою `docs/DEPLOY.md` (сборка, запуск, ENV, cookies, бэкап)
- [x] docker-compose (`docker-compose.yml` в корне): сборка, том `stories-data` (external), `--env-file`, подключение к сети nginx — `docker compose up -d --build` без ручного `docker network connect`
- [x] Конфиг nginx: reverse-proxy по подпути `/instore` — задокументирован (`DEPLOY.md`, `MANUAL_CHECKS.md`) и развёрнут; X-Accel-Redirect — опционально (документирован, `USE_XACCEL=false`, не активирован)
- [x] Прогон end-to-end на реальном URL — подтверждён на сервере: YouTube happy-path (после PR #17, равномерная нарезка до `ready`), Instagram public reel, Instagram с cookies (приватный reel до `ready`; негативная проверка - `AUTH_REQUIRED` без cookies). Сценарий проверки - в `MANUAL_CHECKS.md` (сценарии A и B)

## Реализовано после деплоя

Доработки по результатам эксплуатации (подробности - в `CHANGELOG.md`):

- [x] Поддержка развёртывания под подпутём `ROOT_PATH` (PR #12)
- [x] Умная нарезка: видео ≤ лимита не режется; длинное - на равные части без крошечных «хвостов»; длина сегмента считается по фактической длительности исходника (PR #17)
- [x] Устойчивый селектор формата yt-dlp: фолбэк-ветки вместо `VIDEO_UNAVAILABLE` при отсутствии формата под запрошенный `max_height` (PR #18)
- [x] Шаблон `.env.example` и ужесточение `.dockerignore` (`*.env`) (PR #13/#15)
- [x] Ускорение транскодирования: `-preset veryfast` и явный `-threads 0` для `ffmpeg`/`libx264` (PR #22)
- [x] Настраиваемый пресет транскодера через ENV `TRANSCODE_PRESET` (PR #24)
- [x] Запуск через `docker-compose.yml` в общей сети с nginx (PR #24)
- [x] Ротация логов контейнера: блок `logging` (json-file, `max-size`/`max-file`) в `docker-compose.yml`

## Фаза 8. Фронтенд (клиент)

Решение по стеку и структуре - в [`docs/adr/0001-frontend-architecture.md`](adr/0001-frontend-architecture.md):
Telegram Mini App на TypeScript, монорепо (каталог `frontend/`), публикация
кусков через `shareToStory`.

- [ ] Backend: эндпоинт подписанного URL для кусков (HMAC + TTL, секрет из ENV) - публичная отдача без `X-API-Key` для `shareToStory`
- [ ] Backend: гарантия размера куска ≤ 30 МБ под лимит Stories (size-guard и/или дефолт `max_height` для вертикали)
- [x] Скелет `frontend/` (Svelte + Vite + TS, Telegram WebApp SDK) и CI-джоба: форма URL -> создание задачи -> прогресс (SSE) -> список кусков (скачивание); `shareToStory` подключён, но ждёт публичного URL
- [ ] Генерация типизированного TS-клиента из OpenAPI (пока типы DTO заданы вручную в `frontend/src/lib/types.ts`)
- [ ] Полный сценарий публикации: по готовности `shareToStory` на каждый кусок (после backend-шага с подписанным URL)
- [ ] Деплой статики клиента за nginx (отдельная `location`)

## Открытые вопросы (вести по мере появления)

- [ ] Значение `MAX_VIDEO_DURATION` подтвердить на практике (сейчас 1800 сек, но при лимите 50 МБ фактически ограничивает размер)
- [ ] У Instagram `duration` в метаданных бывает `null` - тогда предварительная проверка `TOO_LONG` пропускается (фактическая длительность берётся по скачанному файлу через ffprobe)
