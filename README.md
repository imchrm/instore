# stories-backend

[![CI](https://github.com/imchrm/instore/actions/workflows/ci.yml/badge.svg)](https://github.com/imchrm/instore/actions/workflows/ci.yml)

Приватный бэкенд-сервис, который по URL видео с YouTube/Instagram скачивает
исходник, перекодирует его в совместимый с Telegram формат с гарантированными
кейфреймами на границах сегмента, нарезает на куски не длиннее 45 секунд без
перекодирования и отдаёт мобильному клиенту манифест и файлы кусков.

Публикацию кусков в Telegram Stories выполняет пользователь вручную из
мобильного клиента; сервер в публикации не участвует.

Сервис для личного использования: без регистрации и мультиарендности,
разграничение доступа - по API-ключам.

## Стек

- Python 3.12+
- FastAPI, Pydantic v2, `pydantic-settings`
- asyncio, SQLite (`aiosqlite`)
- `structlog`
- Внешние инструменты: `yt-dlp`, `ffmpeg`, `ffprobe`
- Качество: `ruff` (lint + format), `mypy --strict`, `pytest`

## Архитектура

Clean Architecture / DDD: зависимости направлены строго внутрь
(interface -> application -> domain; infrastructure реализует порты domain).
Внешние инструменты скрыты за портами и вызываются неблокирующе через
`asyncio`.

```
src/stories_backend/
  domain/          # сущности, перечисления, ошибки, порты (Protocol)
  application/     # сценарии использования и оркестрация конвейера
  infrastructure/  # адаптеры портов (SQLite, ФС, шина событий, yt-dlp, ffmpeg)
  interface/       # HTTP API (FastAPI), конфигурация, DI
  worker/          # in-process asyncio-очередь и планировщик очистки
```

Подробности - в [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); назначение и
границы - в [`docs/CONTEXT.md`](docs/CONTEXT.md).

## Требования

- Python 3.12 или новее.
- Для рантайма обработки видео: `ffmpeg`/`ffprobe` и `yt-dlp`
  (в Docker-образе устанавливаются автоматически, см. `Dockerfile`).

## Установка для разработки

Проект использует src-layout и `hatchling`. Рекомендуется отдельное
виртуальное окружение:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

## Проверки качества

Те же команды выполняются в CI (`.github/workflows/ci.yml`):

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

## Docker

Многоступенчатый образ (`Dockerfile`) собирает зависимости в изолированный
`venv` и добавляет `ffmpeg`/`ffprobe` в рантайм. Точка входа (uvicorn)
появится после реализации HTTP API.

```bash
docker build -t stories-backend .
```

## Статус

Проект развивается по фазам; текущий план и прогресс - в
[`docs/TODO.md`](docs/TODO.md), история изменений - в
[`docs/CHANGELOG.md`](docs/CHANGELOG.md).

## Документация

- [`docs/CONTEXT.md`](docs/CONTEXT.md) - назначение, границы, зафиксированные решения.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - слои, порты, API-контракт, конфигурация, деплой.
- [`docs/TODO.md`](docs/TODO.md) - план работ по фазам.
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) - история изменений.

## Лицензия

Proprietary. Проект приватный, для личного использования.
