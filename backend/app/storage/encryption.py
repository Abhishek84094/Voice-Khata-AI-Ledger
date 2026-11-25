"""Field-level AES-256-GCM encryption for sensitive data at rest (§1 rule 7).

All customer names, amounts, and notes are encrypted before database insertion.
Tokens follow format: 'v1:<key_id>:<base64(nonce_12_bytes + ciphertext_and_tag)>'.
"""

from __future__ import annotations

import base64
import os

from app.core.config import get_settings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptionService:
    """AES-256-GCM encryption service."""

    def __init__(self, key_b64: str | None = None, key_id: str = "k1") -> None:
        raw_key_str = key_b64 or get_settings().ledger_key
        if not raw_key_str:
            # Fallback to dev key if not provided
            raw_key_str = base64.b64encode(b"0" * 32).decode()
        self.key_bytes = base64.b64decode(raw_key_str)
        if len(self.key_bytes) != 32:
            raise ValueError(f"LEDGER_KEY must be exactly 32 bytes (got {len(self.key_bytes)})")
        self.key_id = key_id
        self._aesgcm = AESGCM(self.key_bytes)

    def encrypt_text(self, plaintext: str) -> str:
        """Encrypt plaintext string into versioned token."""
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = base64.b64encode(nonce + ciphertext).decode("ascii")
        return f"v1:{self.key_id}:{payload}"

    def decrypt_text(self, token: str) -> str:
        """Decrypt token back to plaintext string."""
        if not token.startswith("v1:"):
            raise ValueError("Invalid encryption token format")
        parts = token.split(":", 2)
        if len(parts) != 3:
            raise ValueError("Malformed encryption token")
        _, _, payload_b64 = parts
        raw = base64.b64decode(payload_b64.encode("ascii"))
        nonce = raw[:12]
        ciphertext = raw[12:]
        plaintext_bytes = self._aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode("utf-8")

    def encrypt_int(self, value: int) -> str:
        """Encrypt integer into versioned token."""
        return self.encrypt_text(str(value))

    def decrypt_int(self, token: str) -> int:
        """Decrypt token back to integer."""
        text = self.decrypt_text(token)
        return int(text)


_default_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    global _default_service
    if _default_service is None:
        _default_service = EncryptionService()
    return _default_service
