"""
Integração API (option INTEGRACAO_API): the gestor's access keys for the public API and its journal.

A key is «rmk_» + 40 random characters. Only its SHA-256 is stored: the key is shown once, when it is created, and
cannot be read again (a lost key is revoked and replaced). Each key carries its rights (SCOPES) and is limited to
RATE_PER_MINUTE calls; every call is written in the journal, kept JOURNAL_DAYS.
"""
import hashlib
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.api_key import ApiKey, ApiRequestLog

OPTION = "INTEGRACAO_API"
KEY_PREFIX = "rmk_"
SCOPES: dict[str, str] = {
    "catalog": "Catálogo: produtos, serviços, preços e stock",
    "customers": "Clientes: consultar e criar",
    "documents": "Documentos: emitir FT, FR e FP, consultar, PDF e estado AGT",
    "bookings": "Reservas: disponibilidade, criar e cancelar",
}
RATE_PER_MINUTE = 60
JOURNAL_DAYS = 90
MAX_KEYS = 20


class ApiKeyError(Exception):
    """A key refused - the message is shown as it is."""


def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def _view(key: ApiKey) -> dict:
    return {"id": str(key.id), "name": key.name, "prefix": key.prefix, "scopes": list(key.scopes or []),
            "is_active": key.is_active, "created_at": key.created_at, "last_used_at": key.last_used_at,
            "revoked_at": key.revoked_at}


async def list_keys(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(select(ApiKey).where(ApiKey.company_id == company_id)
                             .order_by(ApiKey.is_active.desc(), ApiKey.created_at.desc()))).scalars().all()
    return [_view(k) for k in rows]


async def create_key(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, name: str,
                     scopes: list[str]) -> dict:
    """Returns the key's view plus «key»: the only time the whole key is ever given."""
    name = (name or "").strip()
    if not name:
        raise ApiKeyError("Dê um nome à chave (ex.: Site do hotel)")
    chosen = [s for s in SCOPES if s in set(scopes or [])]
    if not chosen:
        raise ApiKeyError("Escolha pelo menos uma permissão")
    active = (await db.execute(select(ApiKey.id).where(ApiKey.company_id == company_id, ApiKey.is_active.is_(True)))).all()
    if len(active) >= MAX_KEYS:
        raise ApiKeyError(f"No máximo {MAX_KEYS} chaves ativas - revogue uma que já não use")
    plain = KEY_PREFIX + secrets.token_urlsafe(30)[:40]
    key = ApiKey(company_id=company_id, name=name[:100], prefix=plain[:12], key_hash=hash_key(plain), scopes=chosen,
                 created_by_user_id=user_id)
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return {**_view(key), "key": plain}


async def revoke_key(db: AsyncSession, company_id: uuid.UUID, key_id: uuid.UUID) -> dict:
    key = await db.get(ApiKey, key_id)
    if key is None or key.company_id != company_id:
        raise LookupError("Chave não encontrada")
    if key.is_active:
        key.is_active, key.revoked_at = False, datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(key)
    return _view(key)


async def find_key(db: AsyncSession, plain: str) -> ApiKey | None:
    """The key, active or revoked (a revoked key's calls are still written in the journal - refused)."""
    if not plain or not plain.startswith(KEY_PREFIX):
        return None
    return (await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(plain)))).scalar_one_or_none()


# ------------------------------------------------------------------------------------------------------- the limit
# Kept in the memory of the server process: a sliding minute per key. (One process per server - the Windows
# installation, a client's Docker server; on the SaaS the API workers each count their own share.)
_calls: dict[uuid.UUID, deque] = defaultdict(deque)


def within_rate(key_id: uuid.UUID, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    window = _calls[key_id]
    while window and now - window[0] >= 60:
        window.popleft()
    if len(window) >= RATE_PER_MINUTE:
        return False
    window.append(now)
    return True


# ----------------------------------------------------------------------------------------------------- the journal
# its own session, after the answer (the call's session is closed by then); replaced in the tests
journal_session = AsyncSessionLocal


async def write_journal(db: AsyncSession, key: dict, method: str, path: str, status_code: int, duration_ms: int) -> None:
    """key: {"id", "company_id", "name"} - what the guard left on the request (app.api.public_v1.deps)."""
    db.add(ApiRequestLog(company_id=key["company_id"], api_key_id=key["id"], key_name=key["name"], method=method[:8],
                         path=path[:300], status_code=status_code, duration_ms=duration_ms))
    await db.commit()


async def read_journal(db: AsyncSession, company_id: uuid.UUID, key_id: uuid.UUID | None = None, limit: int = 200) -> list[dict]:
    """The latest calls (and the journal's clean-up: what is older than JOURNAL_DAYS goes)."""
    await db.execute(delete(ApiRequestLog).where(
        ApiRequestLog.company_id == company_id,
        ApiRequestLog.created_at < datetime.now(timezone.utc) - timedelta(days=JOURNAL_DAYS)))
    await db.commit()
    query = select(ApiRequestLog).where(ApiRequestLog.company_id == company_id)
    if key_id:
        query = query.where(ApiRequestLog.api_key_id == key_id)
    rows = (await db.execute(query.order_by(ApiRequestLog.created_at.desc()).limit(limit))).scalars().all()
    return [{"key_name": r.key_name, "method": r.method, "path": r.path, "status_code": r.status_code,
             "duration_ms": r.duration_ms, "created_at": r.created_at} for r in rows]
