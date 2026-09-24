# MANUAL_CHECKS — ручная проверка перед деплоем

Документ фиксирует, что уже проверено автоматически в окружении сессии, какие
проверки невозможны здесь (ограничения окружения) и что нужно выполнить вручную
на сервере при развёртывании. Относится к Фазе 6 (тестирование) и Фазе 7
(Docker-образ).

## Что проверено автоматически

Прогон на Python 3.12 (в сессии и в CI):

- `ruff check .` и `ruff format --check .` - без замечаний;
- `mypy .` (strict) - без ошибок;
- `pytest` - unit-тесты всех слоёв (137) + integration-тесты конвейера (2);
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

```sh
docker build -t stories-backend:latest .

docker run -d --name stories-backend \
  -p 8000:8000 \
  -e API_KEYS="mobile:СЕКРЕТНЫЙ_КЛЮЧ" \
  -v stories-data:/data \
  stories-backend:latest

docker ps            # STATUS должен стать healthy (HEALTHCHECK по /health)
docker logs -f stories-backend
```

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
PyPI) либо запустить с `-e YT_DLP_AUTO_UPDATE=true` (обновление на старте,
требует доступа к PyPI). Подробности в `DEPLOY.md`.

## Опционально: nginx и X-Accel-Redirect

Отдача кусков через nginx (разгрузка uvicorn) - вне области Docker-only, но при
наличии nginx на сервере включается так: запустить контейнер с
`-e USE_XACCEL=true` и настроить internal-локацию, совпадающую с
`XACCEL_INTERNAL_PREFIX` (по умолчанию `/_protected`), которая раздаёт файлы из
тома `/data/jobs`. Ориентир:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;              # важно для SSE (/events)
}

location /_protected/ {
    internal;
    alias /path/to/stories-data/jobs/;   # тот же том, что смонтирован в /data
}
```

Точную привязку тома к путям nginx подбирать под конкретный сервер;
приложение лишь возвращает заголовок `X-Accel-Redirect: /_protected/<job>/<file>`.
