"""
Encryption of the secrets kept in the database (the AI provider's API key, later the company's email password and the
channel tokens): never stored in clear, never sent back to a screen. The key is derived from JWT_SECRET_KEY, which every
installation already has - changing JWT_SECRET_KEY makes the stored secrets unreadable: they must then be typed again.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(("rm-soft-secrets:" + get_settings().JWT_SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str | None) -> str | None:
    """The secret in clear, or None when there is none or it cannot be read any more (JWT_SECRET_KEY changed)."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def secret_hint(value: str | None) -> str | None:
    """What a screen may show of a secret: its last 4 characters."""
    return ("•••• " + value[-4:]) if value and len(value) >= 8 else ("••••" if value else None)
