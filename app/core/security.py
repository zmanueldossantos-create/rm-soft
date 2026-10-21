"""
Security module - password hashing and JWT management (access + refresh tokens).
See specification v7, section 2.4 (phone number authentication).
"""
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against the stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, company_id: str, role: str, tenant: str | None = None,
                        support: str | None = None, expires_at: datetime | None = None) -> str:
    """
    Create a short-lived access JWT.
    Embeds company_id (multi-tenant isolation - section 2.5 v7) and role; in SaaS mode the address it was issued for
    (tenant: the company's subdomain, or the admin one) - it is refused on any other address.
    """
    expire = expires_at or datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": subject,
        "company_id": company_id,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if tenant:
        payload["tnt"] = tenant
    if support:  # a support access: the platform user inside a company (see support_service)
        payload["sup"] = support
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str, company_id: str, role: str | None = None, tenant: str | None = None,
                         support: str | None = None, expires_at: datetime | None = None) -> str:
    """Create a long-lived refresh JWT (with the role and the address, to issue the same access token again)."""
    expire = expires_at or datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": subject,
        "company_id": company_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if role:
        payload["role"] = role
    if tenant:
        payload["tnt"] = tenant
    if support:
        payload["sup"] = support
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def issued_before(payload: dict, moment: datetime | None) -> bool:
    """Whether a token was issued before this moment (a password change: older sessions are refused). A token without
    "iat" predates the rule - refused as soon as a password changed."""
    if moment is None:
        return False
    iat = payload.get("iat")
    return iat is None or int(iat) < int(moment.timestamp())


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT. Returns None if invalid or expired."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
