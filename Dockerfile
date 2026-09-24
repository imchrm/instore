# syntax=docker/dockerfile:1

# Multi-stage образ stories-backend.
# Stage builder собирает зависимости в изолированный venv;
# runtime добавляет ffmpeg/ffprobe (системный пакет) и запускает приложение.
# yt-dlp ставится как Python-зависимость проекта в тот же venv.

# --- builder ---------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN python -m venv /opt/venv

# Метаданные сборки и исходники пакета (src-layout).
COPY pyproject.toml ./
COPY src ./src

RUN pip install --upgrade pip && pip install .

# --- runtime ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/data

# ffmpeg включает ffprobe; libx264 (GPL) допустим для приватного использования.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# venv отдаётся пользователю app, чтобы опциональное обновление yt-dlp
# на старте (YT_DLP_AUTO_UPDATE) могло писать в него.
COPY --from=builder --chown=app:app /opt/venv /opt/venv

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Непривилегированный пользователь, каталог данных (том) и права на entrypoint.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p "$DATA_DIR" \
    && chown app:app "$DATA_DIR" \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

USER app
WORKDIR /app

# DATA_DIR — том для SQLite, кусков и cookies (живёт вне слоёв образа).
VOLUME ["/data"]

EXPOSE 8000

# Проверка живости по /api/v1/health (без внешних утилит, через urllib).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)" \
    || exit 1

# entrypoint при YT_DLP_AUTO_UPDATE обновляет yt-dlp, затем запускает CMD.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Точка входа приложения: фабрика create_app (настройки из окружения, в т.ч. API_KEYS).
CMD ["uvicorn", "--factory", "stories_backend.interface.api.app:create_app", \
     "--host", "0.0.0.0", "--port", "8000"]
