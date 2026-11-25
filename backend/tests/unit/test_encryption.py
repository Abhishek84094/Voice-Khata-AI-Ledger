"""Unit tests for AES-256-GCM encryption service."""

import base64

import pytest
from app.storage.encryption import EncryptionService
from cryptography.exceptions import InvalidTag


@pytest.fixture
def enc_service() -> EncryptionService:
    key_32 = base64.b64encode(b"1" * 32).decode()
    return EncryptionService(key_b64=key_32, key_id="test_key")


def test_encryption_roundtrip_text(enc_service: EncryptionService) -> None:
    text = "Ramesh Kumar Sabziwala"
    token = enc_service.encrypt_text(text)
    assert token.startswith("v1:test_key:")
    # Plaintext must not appear in encrypted token
    assert "Ramesh" not in token
    decrypted = enc_service.decrypt_text(token)
    assert decrypted == text


def test_encryption_roundtrip_int(enc_service: EncryptionService) -> None:
    amount_paise = 34000
    token = enc_service.encrypt_int(amount_paise)
    assert "34000" not in token
    decrypted = enc_service.decrypt_int(token)
    assert decrypted == amount_paise


def test_encryption_tamper_detection(enc_service: EncryptionService) -> None:
    token = enc_service.encrypt_text("Secret Data")
    # Tamper with the ciphertext
    prefix, key_id, payload = token.split(":", 2)
    tampered_payload = payload[:-2] + "AA"
    tampered_token = f"{prefix}:{key_id}:{tampered_payload}"

    with pytest.raises(InvalidTag):
        enc_service.decrypt_text(tampered_token)


def test_invalid_key_length() -> None:
    short_key = base64.b64encode(b"short").decode()
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        EncryptionService(key_b64=short_key)
