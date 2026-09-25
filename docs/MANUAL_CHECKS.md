# MANUAL_CHECKS — ручная проверка перед деплоем

Документ фиксирует, что уже проверено автоматически в окружении сессии, какие
проверки невозможны здесь (ограничения окружения) и что нужно выполнить вручную
на сервере при развёртывании. Относится к Фазе 6 (тестирование) и Фазе 7
(Docker-образ).

## Что проверено автоматически

Прогон на Python 3.12 (в сессии и в CI):

- `ruff check .` и `ruff format --check .` - без замечаний;
- `mypy .` (strict) - без ошибок;
- `pytest` - unit-тесты всех слоёв (143) + integration-тесты конвейера (2);
- integration-тест гоняет реальные `ffmpeg`/`ffprobe` на сгенерированном mp4:
  transcode -> segment -> probe -> ready, проверяет длину кусков
  (<= `KEYFRAME_LIMIT_SEC` и <= `segment_time`), manifest и удаление
  промежуточных файлов;
- contract-тест OpenAPI фиксирует набор путей, методы и компоненты-схемы.

CI (`.github/workflows/ci.yml`) ставит `ffmpeg` перед тестами, поэтому
integration-тесты выполняются и в CI.

## Ограничения окружения сессии

Эти проверки в облачной сессии невозможны и вынесены на сервер:

- **Docker (Фаза 7).** В сессии недоступен docker daemon - `docker build` и
  `docker run` не выполнялись. `Dockerfile` проверен статически (ревью),
  `docker-entrypoint.sh` - `sh -n`. Реальную сборку и запуск образа нужно
  выполнить на сервере (шаги ниже).
- **ffmpeg в базовом образе (Фаза 6).** `ffmpeg`/`ffprobe` не входят в образ
  сессии; они были доустановлены (`apt-get install ffmpeg`) только чтобы
  прогнать integration-тесты. В целевом Docker-образе `ffmpeg` ставится на
  шаге runtime.
- **Реальное скачивание.** Прогонов настоящего `yt-dlp` с сетью и реальными
  URL (YouTube/Instagram) не было: integration-тест намеренно подменяет
  скачивание копированием локального файла, чтобы не зависеть от сети и
  внешних сервисов. End-to-end на реальных URL - на стороне сервера.

Без `ffmpeg` набор тестов запускается так: `pytest -m "not integration"`
(integration-тесты будут пропущены; при отсутствии `ffmpeg` они и так
скипаются автоматически).

## Ручная проверка образа на сервере

Предполагается Docker-образ (Фаза 7). Python и SQLite на хосте не нужны -
они внутри образа.

### 1. Сборка и запуск

Переменные окружения задаются через `--env-file` (шаблон - `.env.example` в
корне репозитория; способы передачи и безопасность - в `DEPLOY.md`, раздел
"Где хранить переменные"). Для развёртывания по подпути в файле должно быть
`ROOT_PATH=/instore`.

```sh
docker build -t stories-backend:latest .

# instore.env - копия .env.example вне public/, chmod 600, с реальным API_KEYS
docker run -d --name stories-backend \
  -p 127.0.0.1:8000:8000 \
  --env-file /srv/instore/instore.env \
  -v stories-data:/data \
  stories-backend:latest

docker ps            # STATUS должен стать healthy (HEALTHCHECK по /health)
docker logs -f stories-backend
```

Порт привязан к `127.0.0.1` - контейнер доступен только локально, наружу его
публикует nginx (см. раздел про подпуть ниже). Прямые smoke-проверки ниже
обращаются к контейнеру на `localhost:8000` в обход nginx; `ROOT_PATH` на
маршрутизацию не влияет (эндпоинты всё равно на `/api/v1`), он лишь добавляет
префикс в генерируемые URL кусков и в `/docs`.

### 2. Health и config

```sh
KEY=СЕКРЕТНЫЙ_КЛЮЧ
BASE=http://localhost:8000/api/v1

curl -s "$BASE/health"
curl -s -H "X-API-Key: $KEY" "$BASE/config"
```

### 3. Полный цикл обработки (YouTube)

```sh
# создать задачу
curl -s -X POST "$BASE/jobs" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=XXXX","segment_time":45,"stories_fit":"none"}'
# -> {"job_id":"...","status":"queued",...}

JOB=<job_id из ответа>

# поток прогресса (SSE)
curl -N -H "X-API-Key: $KEY" "$BASE/jobs/$JOB/events"

# статус/манифест
curl -s -H "X-API-Key: $KEY" "$BASE/jobs/$JOB"   # ждём "status":"ready"

# скачать первый кусок
curl -s -H "X-API-Key: $KEY" "$BASE/jobs/$JOB/chunks/0" -o chunk0.mp4
```

### 4. Проверка гарантии длины кусков

После `ready` каждый кусок должен быть не длиннее `segment_time` (45 c) и не
превышать `KEYFRAME_LIMIT_SEC` (60 c). Это как раз тот дефект, что был найден
integration-тестом и исправлен (`-segment_time_delta`). Проверка на хосте
(если есть `ffprobe`) или внутри контейнера:

```sh
# внутри контейнера тома видно как /data/jobs/<job_id>/conv_*.mp4
docker exec stories-backend sh -c \
  'for f in /data/jobs/'"$JOB"'/conv_*.mp4; do \
     echo -n "$f "; ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"; done'
# каждое значение должно быть <= ~45
```

В ответе `GET /jobs/{id}` у кусков поле `over_limit` должно быть `false` у всех.

### 5. Instagram + cookies

```sh
# загрузить cookies.txt (тело запроса = содержимое файла)
curl -s -X POST "$BASE/admin/cookies" \
  -H "X-API-Key: $KEY" --data-binary @cookies.txt

curl -s -H "X-API-Key: $KEY" "$BASE/admin/cookies/status"

# задача с использованием cookies
curl -s -X POST "$BASE/jobs" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://www.instagram.com/reel/XXXX/","use_cookies":true}'
```

### 6. Обновление yt-dlp (при ошибках скачивания)

Если YouTube/Instagram сломали выгрузку - пересобрать образ (свежий `yt-dlp` с
PyPI) либо включить обновление на старте: `YT_DLP_AUTO_UPDATE=true` (в
`--env-file` или разово через `-e`; требует доступа к PyPI). Подробности в
`DEPLOY.md`.

## Развёртывание под подпутём `/instore` за nginx

Сервис - это работающий процесс в контейнере (порт 8000), а не статика; в
`public/instore` его класть не нужно. Снаружи он доступен по подпути через
reverse-proxy nginx. Обязательно задать контейнеру `-e ROOT_PATH=/instore` -
тогда URL кусков в ответах приходят с префиксом (`/instore/api/v1/...`), а
`/docs` и OpenAPI корректны.

```nginx
# Проксирование подпути на контейнер (trailing slash срезает /instore).
location /instore/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;          # важно для SSE (/events)
    proxy_read_timeout 3600s;
}
```

Пример выше подходит, когда nginx запущен на хосте. **Если nginx сам в
контейнере**, `127.0.0.1` внутри него - его собственный loopback, и такой
`proxy_pass` даст `502`. Тогда подключите контейнер сервиса в общую docker-сеть
с nginx и проксируйте по имени - `proxy_pass http://stories-backend:8000/`;
полный порядок действий (общая сеть, `nginx -t`/`reload`, проверка через
`nginx -T | grep instore`) - в `DEPLOY.md`, врезка «Если nginx работает в
контейнере».

Проверка подпути (после запуска с `ROOT_PATH=/instore`):

```sh
KEY=СЕКРЕТНЫЙ_КЛЮЧ
BASE=https://360tur.uz/instore/api/v1

curl -s "$BASE/health"
curl -s -H "X-API-Key: $KEY" "$BASE/config"
# в ответе GET /jobs/{id} поле chunks[].url должно начинаться с /instore/api/v1/...
```

### Опционально: X-Accel-Redirect (разгрузка uvicorn на отдаче кусков)

Включается запуском контейнера с `-e USE_XACCEL=true` и internal-локацией,
совпадающей с `XACCEL_INTERNAL_PREFIX` (по умолчанию `/_protected`). Важно:
эта локация описывается **на корне сервера**, а не внутри `location /instore/` -
nginx резолвит `X-Accel-Redirect` относительно корня.

```nginx
location /_protected/ {
    internal;
    alias /path/to/stories-data/jobs/;   # тот же каталог, что смонтирован в /data/jobs
}
```

Приложение лишь возвращает заголовок `X-Accel-Redirect: /_protected/<job>/<file>`;
точную привязку тома к путям nginx подбирать под конкретный сервер.
