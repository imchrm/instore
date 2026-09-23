# syntax=docker/dockerfile:1

# Заготовка multi-stage образа stories-backend.
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
    PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/data

# ffmpeg включает ffprobe; libx264 (GPL) допустим для приватного использования.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Непривилегированный пользователь и каталог данных (DATA_DIR).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p "$DATA_DIR" \
    && chown app:app "$DATA_DIR"

USER app
WORKDIR /app

EXPOSE 8000

# Заготовка. Реальная точка входа появится после interface/api/app.py:
#   CMD ["uvicorn", "stories_backend.interface.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["python", "-c", "import stories_backend; print('stories-backend', stories_backend.__version__)"]
