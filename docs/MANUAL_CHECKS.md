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

### 3. Сценарий A: YouTube - полный happy-path (до `ready`)

Предусловие: если обновлял код, пересобери образ и **пересоздай** контейнер
(`docker restart` не подхватывает новый образ - см. README/`DEPLOY.md`, раздел
«Обновление образа»):

```sh
cd /opt/360tur/srv/instore \
  && git pull origin main \
  && docker build -t stories-backend:latest . \
  && docker rm -f stories-backend \
  && docker run -d --name stories-backend \
       -p 127.0.0.1:8000:8000 \
       --env-file /srv/instore/instore.env \
       -v stories-data:/data \
       stories-backend:latest
# если nginx в контейнере - вернуть сервис в общую сеть:
docker network connect <сеть_nginx> stories-backend
docker ps --filter name=stories-backend   # STATUS -> healthy
```

Хелпер ожидания готовности (вставить в шелл один раз; использует `KEY`/`BASE`
из шага 2):

```sh
wait_ready() {
  JOB="$1"
  for i in $(seq 1 90); do
    S=$(curl -s -H "X-API-Key: $KEY" "$BASE/jobs/$JOB")
    printf '%s' "$S" | grep -o '"status":"[^"]*"' | head -1
    case "$S" in
      *'"status":"ready"'*)  echo "$S"; return 0 ;;
      *'"status":"failed"'*) echo "$S"; return 1 ;;
    esac
    sleep 2
  done
  echo "timeout"; return 2
}
```

#### A1. Короткий ролик (< 60 c) -> ожидаем один кусок

```sh
RESP=$(curl -s -X POST "$BASE/jobs" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=КОРОТКИЙ","segment_time":45,"stories_fit":"none"}')
echo "$RESP"
JOB=$(printf '%s' "$RESP" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4); echo "JOB=$JOB"

# поток прогресса (SSE) - по желанию, Ctrl+C после ready
curl -N -H "X-API-Key: $KEY" "$BASE/jobs/$JOB/events"

wait_ready "$JOB"
curl -s -H "X-API-Key: $KEY" "$BASE/jobs/$JOB/chunks/0" -o /tmp/c0.mp4 && ls -l /tmp/c0.mp4
```

Критерий A1: `status=ready`, ровно **1** кусок, `over_limit=false`, `url` с
префиксом `/instore/api/v1/...`, кусок скачивается.

#### A2. Длинный ролик (> 60 c, ~3 мин) -> равномерная нарезка

```sh
RESP=$(curl -s -X POST "$BASE/jobs" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=ТРЁХМИНУТНЫЙ","segment_time":45,"max_height":480,"stories_fit":"none"}')
echo "$RESP"
JOB=$(printf '%s' "$RESP" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4); echo "JOB=$JOB"
wait_ready "$JOB"
```

`max_height:480` - чтобы уложиться в `MAX_FILESIZE_MB=50` (иначе `TOO_LARGE`);
при необходимости снизить до 360 или временно поднять лимит в `instore.env` и
пересоздать контейнер.

Критерий A2: `status=ready`, кусков **несколько**, **все** `over_limit=false`,
длительности < 60 c и **равномерны** (без крошечного «хвоста» - подтверждает
PR #17: `92 c -> ~46+46`, а не `45+45+2`).

#### Сводка по задаче

С `jq` (обрати внимание: символ `|` - обычный ASCII):

```sh
curl -s -H "X-API-Key: $KEY" "$BASE/jobs/$JOB" | jq '{
  status,
  chunks: (.chunks | length),
  over_limit: [.chunks[].over_limit],
  durations: [.chunks[].duration_sec],
  urls: [.chunks[].url]
}'
```

Без `jq` - на `grep`:

```sh
S=$(curl -s -H "X-API-Key: $KEY" "$BASE/jobs/$JOB")
printf '%s' "$S" | grep -o '"status":"[^"]*"'
printf '%s' "$S" | grep -o '"index":[0-9]*' | wc -l    # число кусков
printf '%s' "$S" | grep -o '"over_limit":[a-z]*'       # все false
printf '%s' "$S" | grep -o '"url":"[^"]*"'             # с /instore/api/v1/...
```

Через nginx снаружи `BASE=https://360tur.uz/instore/api/v1` - результат тот же,
`chunks[].url` в обоих случаях приходят с префиксом `/instore/...` (`ROOT_PATH`).

### 4. Проверка длительностей и очистки промежуточных файлов

Длительности напрямую по файлам (пока не истёк TTL готовых кусков, 20 мин):

```sh
docker exec stories-backend sh -c \
  "for f in /data/jobs/$JOB/conv_*.mp4; do echo -n \"\$f \"; \
   ffprobe -v error -show_entries format=duration -of csv=p=0 \"\$f\"; done"
```

Ожидаемо: A1 - одна строка ≈ длине ролика; A2 - несколько примерно равных
строк, каждая < 60 c. Правило нарезки после PR #17: видео ≤ `KEYFRAME_LIMIT_SEC`
(60 c) отдаётся одним куском, более длинное режется на равные части (каждая
строго меньше лимита) - поэтому `over_limit=false` у всех и крошечных хвостов
нет.

Очистка промежуточных файлов:

```sh
docker exec stories-backend ls -la /data/jobs/$JOB/
```

Ожидаемо: только `conv_000.mp4` (и далее по индексам) + `manifest.json`. Файлов
`source.*` и `conv.mp4` быть не должно (удаляются после `probe`).

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
