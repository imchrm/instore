"""Подпись временных публичных ссылок на куски (HMAC-SHA256).

Используется, чтобы отдать кусок во внешний сервис (например, Telegram
``shareToStory`` тянет ``media_url`` сам, без ``X-API-Key``). Ссылка содержит срок
действия и подпись; публичный эндпоинт проверяет подпись и срок, не требуя ключа.
Подпись привязана к ``job_id`` + индексу куска + сроку, поэтому не переносится на
другой кусок или задачу.
"""

from __future__ import annotations

import base64
import hashlib
import hmac


class UrlSigner:
    """Подписывает и проверяет кортеж (job_id, index, expires_at)."""

    __slots__ = ("_secret",)

    def __init__(self, secret: str) -> None:
        if not secret:
            msg = "секрет подписи URL не задан"
            raise ValueError(msg)
        self._secret = secret.encode("utf-8")

    def sign(self, job_id: str, index: int, expires_at: int) -> str:
        """Вернуть подпись в urlsafe-base64 без выравнивающих '='."""
        message = _message(job_id, index, expires_at)
        digest = hmac.new(self._secret, message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def verify(self, job_id: str, index: int, expires_at: int, signature: str) -> bool:
        """Проверить подпись за постоянное время (защита от timing-атак)."""
        expected = self.sign(job_id, index, expires_at)
        return hmac.compare_digest(expected, signature)


def _message(job_id: str, index: int, expires_at: int) -> bytes:
    return f"{job_id}:{index}:{expires_at}".encode()
