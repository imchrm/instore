"""Тесты подписанта публичных URL (HMAC)."""

from __future__ import annotations

import pytest

from stories_backend.infrastructure.security.url_signer import UrlSigner


def test_sign_verify_roundtrip() -> None:
    signer = UrlSigner("secret")
    signature = signer.sign("job-1", 0, 1_000)

    assert signer.verify("job-1", 0, 1_000, signature) is True


def test_signature_is_urlsafe_without_padding() -> None:
    signature = UrlSigner("secret").sign("job-1", 0, 1_000)

    assert "=" not in signature
    assert "+" not in signature and "/" not in signature


def test_verify_rejects_tampered_fields() -> None:
    signer = UrlSigner("secret")
    signature = signer.sign("job-1", 0, 1_000)

    assert signer.verify("job-2", 0, 1_000, signature) is False
    assert signer.verify("job-1", 1, 1_000, signature) is False
    assert signer.verify("job-1", 0, 2_000, signature) is False


def test_verify_rejects_other_secret() -> None:
    signature = UrlSigner("secret-a").sign("job-1", 0, 1_000)

    assert UrlSigner("secret-b").verify("job-1", 0, 1_000, signature) is False


def test_empty_secret_rejected() -> None:
    with pytest.raises(ValueError, match="секрет"):
        UrlSigner("")
