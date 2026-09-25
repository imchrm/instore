# DEPLOY — stories-backend (Docker-образ)

Инструкция по сборке и запуску сервиса в виде одного Docker-образа.
Область: только образ (без docker-compose и nginx). Публикация в Stories
не входит в сервис (см. `CHANGELOG.md`, раздел *Out of scope*).

## Что внутри образа

- Базовый образ `python:3.12-slim` (multi-stage: builder -> runtime).
- Системный `ffmpeg` (включает `ffprobe`) для транскодирования и нарезки.
- Изолированный venv в `/opt/venv` с установленным пакетом `stories_backend`
  и его зависимостями (в т.ч. `yt-dlp`).
- Непривилегированный пользователь `app` (uid 1000).
- Том `/data` для SQLite, кусков видео и cookies.
- `HEALTHCHECK` по `GET /api/v1/health`.
- Запуск через `uvicorn --factory stories_backend.interface.api.app:create_app`
  на `0.0.0.0:8000`.

## Сборка

```sh
docker build -t stories-backend:latest .
```

Файл `.dockerignore` оставляет в контексте сборки только `pyproject.toml`,
`src/` и `docker-entrypoint.sh`; тесты, документация и локальные данные
не попадают в образ.

## Запуск

Обязательна переменная `API_KEYS` (пары `имя:ключ` через запятую) и том для
`/data`, чтобы задачи и cookies переживали перезапуск контейнера.

```sh
docker run -d \
  --name stories-backend \
  -p 8000:8000 \
  -e API_KEYS="mobile:СЕКРЕТНЫЙ_КЛЮЧ" \
  -v stories-data:/data \
  stories-backend:latest
```

Проверка после старта:

```sh
curl -H "X-API-Key: СЕКРЕТНЫЙ_КЛЮЧ" http://localhost:8000/api/v1/health
```

## Переменные окружения

Читаются классом `Settings` (Pydantic Settings), имена без учёта регистра.

| Переменная               | По умолчанию   | Назначение                                             |
| ------------------------ | -------------- | ------------------------------------------------------ |
| `API_KEYS`               | (обязательна)  | пары `имя:ключ` через запятую (`key -> key_id`)        |
| `ROOT_PATH`              | `` (корень)    | публичный префикс пути за reverse-proxy, например `/instore` (см. ниже) |
| `DATA_DIR`               | `/data`        | каталог данных (SQLite, куски, cookies); совпадает с томом |
| `COOKIES_DIR`            | `${DATA_DIR}/cookies` | каталог cookies по `key_id`                      |
| `JOB_TTL_SECONDS`        | `1200`         | TTL готовых кусков перед `expired`                      |
| `MAX_CONCURRENT_JOBS`    | `1`            | предел параллельной обработки                           |
| `MAX_FILESIZE_MB`        | `50`           | лимит размера исходного видео                           |
| `MAX_VIDEO_DURATION`     | `1800`         | лимит длительности исходного видео (сек)                |
| `MAX_HEIGHT_DEFAULT`     | `1080`         | ограничение высоты по умолчанию                         |
| `SEGMENT_TIME_DEFAULT`   | `45`           | длина куска (сек)                                       |
| `KEYFRAME_LIMIT_SEC`     | `60`           | предел интервала кейфреймов                             |
| `TARGET_FPS`             | `30`           | целевой FPS при транскодировании                        |
| `CLEANUP_INTERVAL_SEC`   | `60`           | период фоновой очистки по TTL                           |
| `USE_XACCEL`             | `false`        | отдача кусков через `X-Accel-Redirect` (за nginx)       |
| `XACCEL_INTERNAL_PREFIX` | `/_protected`  | internal-префикс локации nginx для `X-Accel-Redirect`   |
| `LOG_LEVEL`              | `INFO`         | уровень логирования                                    |
| `YT_DLP_AUTO_UPDATE`     | (выкл.)        | `1/true/yes` — обновить `yt-dlp` на старте (см. ниже)   |

Замечание про `USE_XACCEL`: при `false` (по умолчанию для одиночного образа)
куски отдаются напрямую через `FileResponse`. Значение `true` предназначено для
работы за nginx с internal-локацией; сам nginx в область этого образа не входит.

### Где хранить переменные

Отдельный `.env` в корне сервера сам по себе не подхватывается: путь `.env` в
приложении относителен рабочему каталогу процесса (`/app` внутри контейнера), а
в образ файл не попадает (он в `.dockerignore`). Поэтому переменные задаются на
уровне Docker при запуске. Способы:

1. **`--env-file` (рекомендуется для нескольких переменных).** Файл лежит на
   хосте, Docker читает его и вкидывает переменные в контейнер:

   ```sh
   docker run -d --name stories-backend \
     -p 127.0.0.1:8000:8000 \
     --env-file /srv/instore/instore.env \
     -v stories-data:/data \
     stories-backend:latest
   ```

   Шаблон всех переменных - в `/.env.example` репозитория; скопируйте его и
   подставьте значения. Формат `--env-file`: строки `KEY=VALUE`, **без кавычек и
   без `export`** (кавычки не срезаются и станут частью значения, например у
   `API_KEYS`).

2. **`-e KEY=value`** прямо в команде. Годится для 2-3 переменных, но секреты
   оседают в истории shell и видны в `docker inspect` - для `API_KEYS` не лучший
   выбор.

3. **Монтирование файла как `/app/.env`** (`-v /srv/instore/instore.env:/app/.env:ro`):
   тогда сработает встроенный `env_file` приложения. Рабочий вариант, но лишняя
   привязка к рабочему каталогу контейнера; предпочтительнее способ 1.

Безопасность: файл с переменными держать **вне** `public/` (иначе его можно
скачать по URL) и вообще вне web-докрута; выставить `chmod 600`; в git он не
должен попадать (в `.gitignore` внесены `.env` и `*.env`, кроме `.env.example`).

## Обновление yt-dlp

YouTube/Instagram часто ломают выгрузку, а `yt-dlp` выпускается часто. Есть два
подхода:

1. **Пересборка образа** (детерминированный образ, рекомендуется для прод):
   периодически выполнять `docker build` заново — свежий `yt-dlp` установится
   из PyPI на шаге builder.
2. **Обновление на старте** (`YT_DLP_AUTO_UPDATE=true`): entrypoint выполнит
   `pip install --upgrade yt-dlp` перед запуском. Обновление best-effort — при
   сбое (например, нет сети) старт продолжится с текущей версией. Требуется
   исходящий доступ к PyPI. Подходит для быстрого реагирования без пересборки.

```sh
docker run -d \
  --name stories-backend \
  -p 8000:8000 \
  -e API_KEYS="mobile:СЕКРЕТНЫЙ_КЛЮЧ" \
  -e YT_DLP_AUTO_UPDATE=true \
  -v stories-data:/data \
  stories-backend:latest
```

## Развёртывание под подпутём (reverse-proxy)

Если сервис доступен снаружи не на своём домене, а по подпути (например
`https://360tur.uz/instore`), нужно:

1. Запустить контейнер с `-e ROOT_PATH=/instore`. Это сообщает FastAPI префикс:
   корректно работают `/docs`, `servers` в OpenAPI и, главное, URL кусков в
   ответах становятся вида `/instore/api/v1/jobs/{id}/chunks/{index}`.
2. Настроить в nginx проксирование подпути на контейнер. Клиент обращается к
   `https://360tur.uz/instore/api/v1/...`, nginx срезает `/instore` и передаёт
   контейнеру `/api/v1/...`.

```sh
docker run -d --name stories-backend \
  -p 127.0.0.1:8000:8000 \
  -e API_KEYS="mobile:СЕКРЕТНЫЙ_КЛЮЧ" \
  -e ROOT_PATH=/instore \
  -v stories-data:/data \
  stories-backend:latest
```

```nginx
# Проксирование подпути на контейнер (trailing slash в proxy_pass срезает /instore).
location /instore/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;          # обязательно для SSE (/events)
    proxy_read_timeout 3600s;     # длинный поток прогресса
}
```

`ROOT_PATH` - единственное, что нужно поменять в приложении: пути файловой
системы контейнера (`/data`, том) от префикса не зависят. Внутренняя локация
для `X-Accel-Redirect` (`/_protected/`, если `USE_XACCEL=true`) описывается на
корне сервера, а не внутри блока `location /instore/` (см. `MANUAL_CHECKS.md`).

Пример выше с `proxy_pass http://127.0.0.1:8000/` подходит, когда **nginx
запущен прямо на хосте**. Если nginx работает в контейнере - см. врезку ниже.

### Если nginx работает в контейнере

Когда nginx сам в контейнере (например, рядом в docker compose), `127.0.0.1`
внутри nginx - это его собственный loopback, а не хост. Опубликованный на хосте
порт `127.0.0.1:8000` из nginx-контейнера по `127.0.0.1` недоступен, и
`proxy_pass http://127.0.0.1:8000/` даст `502`. Правильно - соединить оба
контейнера общей docker-сетью и проксировать по имени контейнера сервиса.

1. Узнать сеть nginx и подключить к ней контейнер сервиса:
   ```sh
   docker inspect <nginx-контейнер> --format '{{json .NetworkSettings.Networks}}'
   docker network connect <имя_сети> stories-backend
   # проверить резолв изнутри nginx:
   docker exec <nginx-контейнер> wget -qO- http://stories-backend:8000/api/v1/health
   ```
   (Чище - объявить `stories-backend` сервисом в том же `docker-compose.yml`:
   тогда общая сеть и DNS по имени сервиса настраиваются автоматически.)

2. В конфиге nginx проксировать по имени контейнера, а не по `127.0.0.1`:
   ```nginx
   location /instore/ {
       proxy_pass http://stories-backend:8000/;   # имя контейнера в общей сети
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_buffering off;          # обязательно для SSE (/events)
       proxy_read_timeout 3600s;
   }
   ```
   Блок помещается в тот `server`-блок, что слушает `443` (рядом с остальными
   `location`); порядок не важен - nginx выбирает самый длинный префикс.

3. Если конфиг nginx смонтирован с хоста (bind-mount `conf.d`), правьте файл на
   хосте и перечитайте конфиг; правка «изнутри» контейнера не переживёт
   пересоздание:
   ```sh
   docker exec <nginx-контейнер> nginx -t
   docker exec <nginx-контейнер> nginx -s reload
   # проверить, что блок загрузился:
   docker exec <nginx-контейнер> nginx -T 2>/dev/null | grep -n instore
   ```
   `nginx -T` печатает конфиг с диска: если `grep` пуст, блок не в том файле,
   что читает контейнер (проверьте `docker inspect <nginx> --format '{{json .Mounts}}'`).

Публикацию `-p 127.0.0.1:8000:8000` можно оставить - удобна для локальных
smoke-проверок с хоста и nginx-контейнеру не мешает.

## Instagram cookies

Для приватного/возрастного контента Instagram нужны cookies. Они загружаются
через админ-эндпоинт и хранятся по `key_id` в `${COOKIES_DIR}` (по умолчанию
`${DATA_DIR}/cookies`, т.е. внутри тома). Использование включается флагом
`use_cookies` при создании задачи. Общий fallback-файл не используется.

## Данные и бэкап

Всё состояние живёт в томе `/data`:

- `jobs.sqlite3` — задачи;
- каталоги задач с готовыми кусками и `manifest.json`;
- `cookies/` — cookies по `key_id`.

Для сохранности достаточно бэкапить том `/data`. Промежуточные файлы удаляются
сразу после `probe`, готовые куски — по истечении `JOB_TTL_SECONDS`.

## Проверка живости

`HEALTHCHECK` в образе опрашивает `http://127.0.0.1:8000/api/v1/health` каждые
30 секунд (`docker ps` показывает `healthy/unhealthy`). Тот же эндпоинт можно
использовать во внешнем оркестраторе или балансировщике.
