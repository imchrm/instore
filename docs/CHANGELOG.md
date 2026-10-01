# CHANGELOG — stories-backend

Все значимые изменения серверной части фиксируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект придерживается [семантического версионирования](https://semver.org/lang/ru/).

## [Unreleased]

### Added

- `docker-compose.yml` в корне репозитория: сборка образа, подключение к общей
  сети nginx (external, по умолчанию `360tur_default`, переопределяется через
  `NGINX_NETWORK`), переиспользование существующего тома `stories-data`
  (external), секреты через `--env-file` (`ENV_FILE`, по умолчанию `instore.env`).
  `docker compose up -d --build` пересобирает и пересоздаёт контейнер в той же
  сети без ручного `docker network connect`. Раздел «Запуск через docker compose»
  в `DEPLOY.md`.
- Настройка `TRANSCODE_PRESET` (ENV): пресет `libx264` (`ultrafast`..`placebo`,
  по умолчанию `veryfast`) с валидацией значения в `Settings`; прокидывается в
  `FfmpegTranscoder`. Позволяет менять компромисс скорость/битрейт без правок
  кода. Отражено в `.env.example`, `DEPLOY.md` и `ARCHITECTURE.md`.
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
- Слой infrastructure (Фаза 2, часть 1) - адаптеры без внешних бинарников:
  `security/api_keys.py` (реестр `ключ -> key_id`, без утечки ключей в `repr`),
  `storage/filesystem_storage.py` (каталоги задач, удаление промежуточных/всей задачи),
  `cookies/filesystem_cookies.py` (атомарная запись, права 0600, статус/удаление),
  `persistence/sqlite_repo.py` (`JobRepositoryPort` на aiosqlite, миграция схемы),
  `events/sse_bus.py` (внутрипроцессная шина событий с ранней регистрацией подписки).
- Unit-тесты адаптеров и статическая проверка их соответствия портам (mypy).
- Слой infrastructure (Фаза 2, часть 2) - процессные адаптеры внешних инструментов:
  `process/runner.py` (инъектируемый `ProcessRunner` поверх asyncio subprocess),
  `media/ffprobe_probe.py` (длительность файла),
  `media/ffmpeg_segmenter.py` (нарезка `-c copy -f segment`, список кусков),
  `media/ffmpeg_transcoder.py` (transcode с `force_key_frames`, фильтрами `stories_fit`, прогресс из `-progress pipe:1`),
  `downloader/ytdlp.py` (`probe_meta`/`download` с ограничениями и cookies, прогресс, маппинг ошибок yt-dlp в `ErrorCode`).
- Unit-тесты процессных адаптеров на фейковом раннере (без реальных ffmpeg/yt-dlp).
- `README.md`: обзор проекта, стек, структура, установка и проверки.
- Слой application (Фаза 3, часть 1) - сценарии без оркестрации:
  `config.py` (`ProcessingLimits` - лимиты/дефолты из ENV-таблицы),
  `ports.py` (`JobSubmitterPort`, типы `Clock`/`IdGenerator`),
  `create_job` (регистрация + постановка в очередь),
  `get_job`/`delete_job`/`stream_progress` (изоляция по `key_id`),
  `cleanup_expired` (перевод `ready` в `expired` по TTL),
  `cookies_admin` (upload/status/delete cookies).
- Unit-тесты сценариев на общих in-memory fake-портах (`tests/port_fakes.py`).
- Слой application (Фаза 3, часть 2) - оркестрация конвейера:
  `services/job_processing.py` (`JobProcessingService.process`: фазы
  download -> transcode -> segment -> probe -> ready, обновление статусов и
  прогресса через шину и репозиторий, проверки лимитов `TOO_LARGE`/`TOO_LONG`,
  разрешение cookies `AUTH_REQUIRED`, подсчёт sha256/размеров кусков и запись
  `manifest.json`, перевод в `FAILED` при любой доменной ошибке),
  `use_cases/process_job.py` (загрузка задачи по id и запуск конвейера).
- Unit-тесты оркестрации на fake-адаптерах (happy path, over_limit,
  `AUTH_REQUIRED`, `TOO_LARGE`, `TOO_LONG`, сбой скачивания). С этим слой
  application (Фаза 3) завершён.
- Слой worker (Фаза 4):
  `worker/queue.py` (`JobQueue` - `JobSubmitterPort` на `asyncio.Queue` с
  фоновым потребителем и семафором `max_concurrent_jobs`),
  `worker/scheduler.py` (`PeriodicCleanupScheduler` - периодический запуск
  очистки по TTL, отдельный `run_once`),
  `application/use_cases/recover_interrupted.py` (`RecoverInterruptedUseCase` -
  пометка прерванных рестартом задач как `FAILED (INTERNAL)`).
  Добавлен порт `JobRepositoryPort.list_unfinished` и `JobProcessorPort`.
- Unit-тесты воркера: порядок обработки, ограничение параллелизма,
  восстановление только in-flight задач, один проход и жизненный цикл планировщика.
- Слой interface (Фаза 5, часть 1) - HTTP-каркас:
  `interface/config.py` (Pydantic Settings по таблице ENV; `to_limits`),
  `interface/api/schemas.py` (DTO запросов/ответов), `mappers.py` (domain -> DTO),
  `container.py` + `deps.py` (DI-контейнер, аутентификация `X-API-Key` -> `key_id`),
  `interface/api/app.py` (`create_app` + `lifespan`: сборка адаптеров/сценариев,
  восстановление прерванных задач, запуск воркера и планировщика),
  роутер `system` (`/api/v1/health`, `/api/v1/config`).
- Unit-тесты: настройки, мапперы и приложение (жизненный цикл, `/health`, `/config`)
  через `TestClient`. Роутеры `jobs`/`admin` - в части 2.
- Слой interface (Фаза 5, часть 2) - роутеры бизнес-логики:
  `routers/jobs.py` (`POST /jobs`, `GET /jobs/{id}`, `DELETE /jobs/{id}`,
  `GET /jobs/{id}/events` - SSE, `GET /jobs/{id}/chunks/{index}` - отдача
  кусков через `X-Accel-Redirect` в prod / `FileResponse` в dev),
  `routers/admin.py` (cookies upload/status/delete). С этим слой interface
  (Фаза 5) и основной функционал сервиса завершены.
- `Dockerfile`: точка входа переключена на `uvicorn --factory create_app`.
- Unit-тесты роутеров на приложении с fake-контейнером (аутентификация,
  изоляция по `key_id`, валидация тела, отдача кусков, формат SSE).
- Деплой (Фаза 7, только Docker-образ):
  финализация `Dockerfile` (том `/data`, непривилегированный пользователь
  `app`, `HEALTHCHECK` по `/api/v1/health`, entrypoint),
  `docker-entrypoint.sh` (опциональное обновление `yt-dlp` по
  `YT_DLP_AUTO_UPDATE`, затем запуск `CMD`),
  `.dockerignore` (минимальный контекст сборки: `pyproject.toml`, `src`,
  entrypoint),
  `docs/DEPLOY.md` (сборка, запуск, таблица ENV, обновление `yt-dlp`,
  cookies, бэкап тома, проверка живости).
- Тестирование и качество (Фаза 6):
  integration-тест сквозного конвейера transcode -> segment -> probe -> ready
  на реальных `ffmpeg`/`ffprobe` (короткий mp4 генерируется в фикстуре,
  скачивание подменяется копированием локального файла), маркер `integration`
  и его пропуск при отсутствии бинарников;
  contract-тест OpenAPI/DTO (фиксирует набор путей, методы и компоненты-схемы);
  шаг установки `ffmpeg` в CI перед тестами.
- Инструкция ручной проверки перед деплоем: `docs/MANUAL_CHECKS.md`
  (что проверяется в окружении сессии, а что - на сервере пользователя;
  ограничения окружения по Фазам 6 и 7).
- Врезка «Если nginx работает в контейнере» в `DEPLOY.md` (и указатель в
  `MANUAL_CHECKS.md`): общая docker-сеть + `proxy_pass http://stories-backend:8000`
  по имени контейнера вместо `127.0.0.1`, порядок `nginx -t`/`reload` и проверка
  `nginx -T | grep instore`.
- Развёртывание под подпутём за reverse-proxy: настройка `ROOT_PATH`
  (например `/instore`) - прокидывается в `FastAPI(root_path=...)` (корректные
  `/docs` и OpenAPI), а URL кусков в ответах формируются с этим префиксом
  (`/instore/api/v1/jobs/{id}/chunks/{index}`). Инструкции по nginx в
  `DEPLOY.md` и `MANUAL_CHECKS.md`.
- Шаблон переменных окружения `.env.example` (все переменные со значениями по
  умолчанию, без секретов) и подраздел `DEPLOY.md` "Где хранить переменные"
  (способы передачи в контейнер: `--env-file` / `-e` / монтирование, формат и
  безопасность). В `.gitignore` внесены `.env` и `*.env` (кроме `.env.example`).
- Заметка про обновление образа (`README.md`, `DEPLOY.md`): `docker restart` не
  подхватывает пересобранный образ - контейнер нужно пересоздавать (`rm` + `run`,
  либо `docker compose up -d --build`), после пересоздания вернуть в сеть nginx.
- `MANUAL_CHECKS.md`, §3-§4: полноценный сценарий A (YouTube happy-path) с
  предусловием-пересозданием контейнера (не `restart`), хелпером `wait_ready`,
  кейсами A1 (короткий ролик -> 1 кусок) и A2 (длинный -> равномерная нарезка),
  авто-извлечением `job_id`, сводкой на `jq`/`grep` и проверкой длительностей
  (ffprobe) и очистки промежуточных файлов с учётом правила нарезки PR #17.
- `TODO.md` синхронизирован с текущим состоянием: nginx reverse-proxy (подпуть
  `/instore`) отмечен как задокументированный и развёрнутый (X-Accel-Redirect -
  опция); end-to-end уточнён (YouTube happy-path подтверждён после PR #17,
  Instagram public подтверждён, Instagram с cookies - предстоит); добавлен раздел
  «Реализовано после деплоя» (PR #12/#13/#15/#17/#18) и заметка про Instagram
  `duration:null` в открытых вопросах.
- `MANUAL_CHECKS.md`: §5 развёрнут в полноценный сценарий B (Instagram с cookies)
  с шагами B1-B5 (подготовка `cookies.txt`, upload/status, задача `use_cookies`
  до `ready`, негативная проверка `AUTH_REQUIRED` без cookies, удаление cookies);
  добавлен раздел «Очередь и наблюдение за задачами» (один воркер и FIFO,
  отсутствие эндпоинта списка, `docker top`/SQLite/логи, in-memory очередь не
  переживает пересоздание контейнера); хелпер `wait_ready` получил параметр
  бюджета и пояснение, что его `timeout` - клиентский, а не ошибка обработки.
- `TODO.md`: end-to-end (Фаза 7) закрыт как подтверждённый на сервере - YouTube
  happy-path, Instagram public и Instagram с cookies (приватный reel до `ready`,
  негатив `AUTH_REQUIRED`); в «Реализовано после деплоя» добавлено ускорение
  транскодирования (PR #22).

### Fixed

- Нарезка сегментов: муксер `segment` пропускал кейфрейм ровно на границе
  сегмента (сравнение "строго позже" + погрешность float) и выдавал куски
  двойной длины, нарушая гарантию `KEYFRAME_LIMIT_SEC`. Добавлен
  `-segment_time_delta` в `FfmpegSegmenter`; дефект выявлен integration-тестом.
- `.dockerignore`: правило `.env` заменено на `*.env`, чтобы env-файлы рядом с
  исходниками (например `instore.env` при сборке в каталоге репозитория) не
  попадали в контекст сборки; шаблон `.env.example` под шаблон не подпадает.
- yt-dlp: селектор формата стал устойчивее - добавлены безусловные фолбэк-ветки
  (`.../bv*+ba/b`). Раньше при отсутствии формата под запрошенный `max_height`
  (например у Instagram минимальная высота выше запрошенной, либо высота не
  указана в метаданных) задача падала с `VIDEO_UNAVAILABLE`; теперь берётся
  лучший доступный формат, а ограничение размера сохраняется через
  `--max-filesize`.

### Changed

- Транскодирование: добавлены `-preset veryfast` и явный `-threads 0` в вызов
  `ffmpeg`/`libx264`. На скромных CPU (VPS) кодирование ускоряется в несколько
  раз ценой небольшого роста битрейта; профиль (`high`), пиксельный формат и
  форсирование кейфреймов на границах сегмента не меняются, поэтому нарезка
  копированием потока и совместимость с Telegram сохраняются.
- Логика нарезки: если всё видео умещается в предел куска (`KEYFRAME_LIMIT_SEC`,
  по умолчанию 60 c) - оно отдаётся одним куском, без нарезки. Более длинные
  ролики режутся на равные части (каждая строго меньше предела, с целевой
  гранулярностью `segment_time`), что исключает крошечные «хвосты» (например
  47 c -> 1 кусок вместо 45+2; 92 c -> равные части, а не 45+45+2). Длина
  сегмента считается по фактической длительности исходника (ffprobe), что
  надёжнее метаданных (у Instagram `duration` бывает `null`). Функция
  `plan_segment_seconds`; порты transcoder/segmenter принимают дробную длину.

### Decided

- Очередь и хранение: in-process asyncio-воркер + SQLite; без arq/Redis.
- Лимит исходного видео `MAX_FILESIZE_MB = 50` с проверкой по метаданным и через `--max-filesize`.
- Ограничение высоты по умолчанию 1080p.
- TTL готовых кусков 1200 секунд; промежуточные файлы удаляются сразу после `probe`.
- Нарезка: видео до предела куска (`KEYFRAME_LIMIT_SEC`, 60 c) отдаётся одним куском; более длинное режется на равные части (каждая строго меньше предела, целевая гранулярность `segment_time`) с гарантией границ через принудительные кейфреймы на шаге transcode.
- Приведение под Stories параметром `stories_fit: none | cover | pad` (по умолчанию `none`).
- Аутентификация по `X-API-Key`; несколько ключей (пары `имя:ключ`).
- Изоляция задач по `key_id`.
- Instagram cookies хранятся по `key_id`; общий fallback-файл не используется; загрузка вне основного потока, использование по флагу `use_cookies`.

### Out of scope

- Автоматическая публикация в Telegram Stories (userbot/MTProto) исключена; порт публикации не закладывается.

[Unreleased]: about:blank
