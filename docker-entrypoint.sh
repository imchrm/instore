#!/bin/sh
# Точка входа контейнера stories-backend.
# При YT_DLP_AUTO_UPDATE (1/true/yes) обновляет yt-dlp перед запуском,
# затем передаёт управление команде образа (CMD).
set -eu

case "${YT_DLP_AUTO_UPDATE:-}" in
    1 | true | TRUE | yes | YES)
        echo "docker-entrypoint: обновление yt-dlp..." >&2
        pip install --no-cache-dir --upgrade yt-dlp \
            || echo "docker-entrypoint: не удалось обновить yt-dlp, продолжаю с текущей версией" >&2
        ;;
    *)
        : # обновление отключено (по умолчанию) - детерминированный образ
        ;;
esac

exec "$@"
