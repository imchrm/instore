# ARCHITECTURE — stories-backend

Архитектура серверной части: слои, порты и адаптеры, модель данных, автомат состояний,
конвейер обработки, API-контракт, конфигурация, хранилище и развёртывание.

- Модуль: `stories-backend`
- Стек: Python 3.12+, FastAPI, Pydantic v2, asyncio, SQLite
- Качество: `mypy --strict`, `ruff` (lint + format), полные аннотации типов
- Кодировка: UTF-8; без эмодзи в коде и документации

## 1. Принципы

- Clean Architecture / DDD: зависимости направлены строго внутрь (interface → application → domain; infrastructure реализует порты domain).
- Внешние инструменты (`yt-dlp`, `ffmpeg`, `ffprobe`) скрыты за портами domain и вызываются неблокирующе через `asyncio` subprocess.
- Границы типизированы Pydantic-моделями; domain оперирует собственными сущностями, не DTO транспорта.
- Побочные эффекты (файлы, процессы, БД, шина событий) — только в infrastructure.

## 2. Слои и структура каталогов

```
src/stories_backend/
  domain/
    entities.py         # Job, Chunk, VideoMeta
    enums.py            # JobStatus, ErrorCode, StoriesFit
    errors.py           # доменные исключения
    ports.py            # Protocol/ABC портов
  application/
    use_cases/
      create_job.py
      process_job.py
      get_job.py
      stream_progress.py
      delete_job.py
      cleanup_expired.py
      cookies_admin.py
    services/
      job_processing.py # оркестрация конвейера
  infrastructure/
    downloader/ytdlp.py
    media/ffmpeg_transcoder.py
    media/ffmpeg_segmenter.py
    media/ffprobe_probe.py
    persistence/sqlite_repo.py
    events/sse_bus.py
    storage/filesystem_storage.py
    cookies/filesystem_cookies.py
    security/api_keys.py
  interface/
    api/
      app.py            # сборка FastAPI, lifespan, DI
      deps.py           # зависимости, аутентификация
      routers/jobs.py
      routers/admin.py
      routers/system.py # /config, /health
      schemas.py        # DTO запросов/ответов
      mappers.py        # domain <-> DTO
    config.py           # чтение и валидация ENV (Pydantic Settings)
  worker/
    queue.py            # in-process asyncio очередь и воркер
    scheduler.py        # периодическая очистка по TTL
tests/
  unit/
  integration/
```

Зависимости: `domain` не импортирует ничего из проекта; `application` зависит только от `domain`; `infrastructure` и `interface` зависят от `application`/`domain`; сборка графа зависимостей — в `interface/api/app.py`.

## 3. Доменная модель

```python
from dataclasses import dataclass, field

@dataclass(slots=True)
class Chunk:
    index: int
    filename: str
    duration_sec: float
    size_bytes: int
    sha256: str
    over_limit: bool

@dataclass(slots=True)
class VideoMeta:
    title: str | None
    duration_sec: float | None
    filesize_bytes: int | None
    height: int | None

@dataclass(slots=True)
class Job:
    job_id: str
    key_id: str
    url: str
    segment_time: int
    max_height: int
    stories_fit: "StoriesFit"
    use_cookies: bool
    status: "JobStatus"
    progress: float = 0.0
    meta: VideoMeta | None = None
    chunks: list[Chunk] = field(default_factory=list)
    error_code: "ErrorCode | None" = None
    error_message: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
```

Перечисления:

```python
from enum import StrEnum

class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCODING = "transcoding"
    SEGMENTING = "segmenting"
    PROBING = "probing"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"

class StoriesFit(StrEnum):
    NONE = "none"
    COVER = "cover"
    PAD = "pad"

class ErrorCode(StrEnum):
    URL_UNSUPPORTED = "URL_UNSUPPORTED"
    VIDEO_UNAVAILABLE = "VIDEO_UNAVAILABLE"
    VIDEO_PRIVATE = "VIDEO_PRIVATE"
    GEO_BLOCKED = "GEO_BLOCKED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    TOO_LONG = "TOO_LONG"
    TOO_LARGE = "TOO_LARGE"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    TRANSCODE_FAILED = "TRANSCODE_FAILED"
    SEGMENT_FAILED = "SEGMENT_FAILED"
    INTERNAL = "INTERNAL"
```

## 4. Порты (domain/ports.py)

```python
from typing import Protocol, AsyncIterator

class VideoDownloaderPort(Protocol):
    async def probe_meta(self, url: str, *, cookies_path: str | None) -> VideoMeta: ...
    async def download(
        self, url: str, dest_dir: str, *,
        max_height: int, max_filesize_mb: int, cookies_path: str | None,
        on_progress: "ProgressCallback",
    ) -> str: ...  # путь к скачанному файлу

class TranscoderPort(Protocol):
    async def transcode(
        self, src: str, dest: str, *,
        segment_time: int, fps: int, stories_fit: StoriesFit,
        on_progress: "ProgressCallback",
    ) -> None: ...

class SegmenterPort(Protocol):
    async def segment(self, src: str, out_pattern: str, *, segment_time: int) -> list[str]: ...

class MediaProbePort(Protocol):
    async def duration_sec(self, path: str) -> float: ...

class JobRepositoryPort(Protocol):
    async def add(self, job: Job) -> None: ...
    async def get(self, job_id: str) -> Job | None: ...
    async def update(self, job: Job) -> None: ...
    async def delete(self, job_id: str) -> None: ...
    async def list_expired(self, ttl_seconds: int) -> list[Job]: ...

class EventBusPort(Protocol):
    async def publish(self, job_id: str, event: "ProgressEvent") -> None: ...
    def subscribe(self, job_id: str) -> AsyncIterator["ProgressEvent"]: ...

class StoragePort(Protocol):
    def job_dir(self, job_id: str) -> str: ...
    async def remove_job(self, job_id: str) -> None: ...
    async def remove_intermediate(self, job_id: str) -> None: ...

class CookiesStorePort(Protocol):
    async def save(self, key_id: str, content: bytes) -> None: ...
    async def path(self, key_id: str) -> str | None: ...
    async def status(self, key_id: str) -> "CookiesStatus": ...
    async def delete(self, key_id: str) -> None: ...
```

`ProgressCallback` — `Callable[[float, str | None], Awaitable[None]]` (доля фазы 0..1 и опциональное сообщение).

Осознанно отсутствует: порт публикации в Stories. Авто-постинг вне области проекта.

## 5. Конвейер обработки

Оркестратор `JobProcessingService.process(job)` выполняет фазы последовательно, на каждой обновляя статус и прогресс через `EventBusPort` и `JobRepositoryPort`.

1. DOWNLOADING
   - Разрешить cookies: если `use_cookies=true`, взять `CookiesStorePort.path(key_id)`; нет файла → `AUTH_REQUIRED`.
   - `probe_meta`: если размер известен и > `MAX_FILESIZE_MB` → `TOO_LARGE`; если длительность > `MAX_VIDEO_DURATION` → `TOO_LONG`.
   - `download` с `--max-filesize {MAX_FILESIZE_MB}M` и ограничением высоты; прерывание по размеру → `TOO_LARGE`.
2. TRANSCODING
   ```
   ffmpeg -i <src> -c:v libx264 -profile:v high -pix_fmt yuv420p -r {fps} \
     [<фильтр stories_fit>] \
     -force_key_frames "expr:gte(t,n_forced*{segment_time})" \
     -c:a aac -b:a 128k -movflags +faststart -progress pipe:1 <conv.mp4>
   ```
   Фильтр по `stories_fit`:
   - `none` — фильтр не добавляется.
   - `cover` — `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`.
   - `pad` — размытый фон + вписанное видео до 1080x1920 (два потока: масштаб+блюр фона и `overlay` исходного по центру).
3. SEGMENTING
   ```
   ffmpeg -i <conv.mp4> -c copy -map 0 -segment_time {segment_time} \
     -f segment -reset_timestamps 1 <conv_%03d.mp4>
   ```
4. PROBING
   - Для каждого куска `ffprobe`: длительность и размер; `sha256`; `over_limit = duration > KEYFRAME_LIMIT_SEC`.
   - Сформировать и записать `manifest.json`.
   - `StoragePort.remove_intermediate(job_id)` — удалить `source.*` и `conv.mp4`.
5. READY — задача готова; `updated_at` фиксирует момент готовности (точка отсчёта TTL).

Любая фаза при исключении переводит задачу в FAILED с соответствующим `ErrorCode` и сообщением; дочерние процессы завершаются.

## 6. Автомат состояний

```
queued -> downloading -> transcoding -> segmenting -> probing -> ready -> expired
   \___________\_____________\____________\___________\___-> failed
```

- В `failed` — из любой рабочей фазы.
- В `expired` — из `ready` по TTL (фоновый планировщик).
- Повторный запуск не предусмотрен: клиент создаёт новую задачу.

## 7. Очередь и планировщик

- `worker/queue.py`: `asyncio.Queue` + один воркер-таск, запускаемый в `lifespan` FastAPI. Параллелизм ограничен `MAX_CONCURRENT_JOBS` (по умолчанию 1) семафором.
- При старте приложения незавершённые задачи из SQLite (`downloading/transcoding/...`) помечаются `failed` (`INTERNAL`, «прервано рестартом»), чтобы не висели вечно.
- `worker/scheduler.py`: периодический таск раз в N секунд вызывает `CleanupExpiredUseCase` — переводит просроченные `ready` в `expired` и удаляет их файлы.

## 8. API-контракт

Базовый префикс `/api/v1`. Все тела — Pydantic v2. Аутентификация по `X-API-Key` для всех эндпоинтов, кроме `/health` и `/config`.

### DTO

```python
class JobCreateRequest(BaseModel):
    url: HttpUrl
    segment_time: int = Field(default=45, ge=5, le=60)
    max_height: int = Field(default=1080, ge=240, le=2160)
    stories_fit: StoriesFit = StoriesFit.NONE
    use_cookies: bool = False

class ChunkInfo(BaseModel):
    index: int
    filename: str
    url: str
    duration_sec: float
    size_bytes: int
    sha256: str
    over_limit: bool

class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    source_title: str | None = None
    source_duration_sec: float | None = None
    progress: float = 0.0
    chunks: list[ChunkInfo] = []
    error: ErrorInfo | None = None
    created_at: float
    updated_at: float

class ProgressEvent(BaseModel):
    job_id: str
    status: JobStatus
    phase_progress: float
    message: str | None = None

class CookiesStatus(BaseModel):
    present: bool
    uploaded_at: float | None = None
    likely_expired: bool = False

class ServiceConfig(BaseModel):
    max_filesize_mb: int
    max_height_default: int
    segment_time_default: int
    keyframe_limit_sec: int
    stories_fit_options: list[StoriesFit]
    job_ttl_seconds: int
```

### Эндпоинты

| Метод | Путь | Назначение | Ответ |
|---|---|---|---|
| POST | `/api/v1/jobs` | Создать задачу | 202 `JobResponse` |
| GET | `/api/v1/jobs/{id}` | Статус/манифест | 200 `JobResponse` / 404 |
| GET | `/api/v1/jobs/{id}/events` | SSE прогресс | 200 `text/event-stream` |
| GET | `/api/v1/jobs/{id}/chunks/{index}` | Файл куска | 200 `video/mp4` / 404 |
| DELETE | `/api/v1/jobs/{id}` | Удалить задачу | 204 / 404 |
| POST | `/api/v1/admin/cookies` | Загрузить cookies.txt | 204 |
| GET | `/api/v1/admin/cookies/status` | Состояние cookies | 200 `CookiesStatus` |
| DELETE | `/api/v1/admin/cookies` | Удалить cookies | 204 |
| GET | `/api/v1/config` | Лимиты и дефолты | 200 `ServiceConfig` |
| GET | `/api/v1/health` | Здоровье сервиса | 200 |

Правила доступа:

- Все `/jobs/*` работают только с задачами, у которых `job.key_id == текущий key_id` (изоляция по ключу). Чужая задача → 404 (не 403, чтобы не раскрывать существование).
- `/admin/cookies*` работают только с файлом текущего `key_id`.
- `/jobs/{id}/chunks/{index}` в продакшене возвращает пустой ответ с заголовком `X-Accel-Redirect` на internal-локацию nginx; в dev — `FileResponse`. Управляется `USE_XACCEL`.

Коды ошибок HTTP: 401 (нет/неверный `X-API-Key`), 404 (нет задачи в пределах ключа), 413 или доменный `TOO_LARGE` в теле `JobResponse` при превышении размера, 422 (валидация запроса), 503 (`/health` при недоступности `yt-dlp`/`ffmpeg`/`ffprobe`).

### SSE

`GET /jobs/{id}/events` отдаёт поток событий `ProgressEvent` (JSON в поле `data`). Клиент закрывает поток при `status in {ready, failed, expired}`. Резервный путь — поллинг `GET /jobs/{id}`.

## 9. Хранилище

```
DATA_DIR/
  jobs.sqlite3
  jobs/{job_id}/
    source.*          # удаляется после probe
    conv.mp4          # удаляется после probe
    conv_000.mp4 ...  # куски, живут до TTL
    manifest.json
  cookies/{key_id}.txt   # права 0600, вне nginx-раздачи
```

`manifest.json` — сериализованный `JobResponse` без транспортных URL либо с относительными путями кусков.

## 10. Конфигурация (ENV, Pydantic Settings)

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `API_KEYS` | пары `имя:ключ` через запятую | (обязательно) |
| `DATA_DIR` | корень данных | `/data` |
| `COOKIES_DIR` | каталог cookies | `${DATA_DIR}/cookies` |
| `JOB_TTL_SECONDS` | TTL готовых кусков | `1200` |
| `MAX_CONCURRENT_JOBS` | параллелизм обработки | `1` |
| `MAX_FILESIZE_MB` | лимит исходника | `50` |
| `MAX_VIDEO_DURATION` | лимит длительности исходника, сек | `1800` |
| `MAX_HEIGHT_DEFAULT` | ограничение высоты | `1080` |
| `SEGMENT_TIME_DEFAULT` | длина куска, сек | `45` |
| `KEYFRAME_LIMIT_SEC` | предел куска (флаг over_limit) | `60` |
| `TARGET_FPS` | fps при перекодировании | `30` |
| `CLEANUP_INTERVAL_SEC` | период планировщика очистки | `60` |
| `USE_XACCEL` | отдача файлов через nginx | `false` |
| `XACCEL_INTERNAL_PREFIX` | internal-локация nginx | `/_protected` |
| `LOG_LEVEL` | уровень логирования | `INFO` |

`API_KEYS` парсится в отображение `key -> key_id` (из имени). Значения ключей и содержимое cookies никогда не попадают в логи.

## 11. Наблюдаемость

- Структурные логи (`structlog` или `loguru`) с `job_id` и `key_id` в контексте.
- `/health` проверяет наличие и версии `yt-dlp`, `ffmpeg`, `ffprobe`, доступность `DATA_DIR` и SQLite.

## 12. Развёртывание

- Docker, multi-stage. В рантайм-образ ставятся `ffmpeg`/`ffprobe` и `yt-dlp`.
- Обновление `yt-dlp`: пересборка образа по расписанию либо отдельный шаг обновления при старте контейнера (закрепить в TODO).
- nginx перед сервисом: публичные эндпоинты проксируются, internal-локация `XACCEL_INTERNAL_PREFIX` отдаёт файлы кусков из `DATA_DIR/jobs`.
- Примечание по лицензии: `libx264` — GPL; для приватного использования ограничений нет.

## 13. Тестирование

- Unit: сценарии `application` с fake-портами — корректность автомата статусов, обработка ошибок (`TOO_LARGE`, `AUTH_REQUIRED` и т.д.), формирование манифеста, изоляция по `key_id`.
- Integration: прогон конвейера на коротком тестовом mp4 (fixture в репозитории) — число кусков, все ≤ `KEYFRAME_LIMIT_SEC`, корректность `manifest.json`.
- Contract: валидация OpenAPI-схемы и DTO.
- CI-гейт: `ruff`, `mypy --strict`, `pytest`.
