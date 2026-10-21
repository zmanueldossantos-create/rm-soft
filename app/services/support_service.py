"""
Accesso de suporte: the platform (SUPER_ADMIN) enters a client company with the gestor's screens - with a reason, for
SUPPORT_MINUTES at most, through a one-time code that opens the company's own address (SaaS: its subdomain; local: the
same application). No company account is created and no password is shared. Every entry is kept and shown to the
company's gestor; what is done meanwhile is recorded in the platform user's own name (the session's user is him).
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token
from app.models.company import Company
from app.models.support_session import SupportSession
from app.models.user import User, UserRole

SUPPORT_MINUTES = 60
CODE_SECONDS = 120
MIN_REASON = 10


class SupportError(Exception):
    """The support access is refused - the message is shown as it is (PT-PT)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def is_active(session: SupportSession | None) -> bool:
    return session is not None and session.ended_at is None and session.expires_at > _now()


async def start_support(db: AsyncSession, admin: User, company_id: uuid.UUID, reason: str) -> dict:
    """Opens a support access to the company: returns the one-time code (valid CODE_SECONDS) and the company's address."""
    reason = " ".join((reason or "").split())
    if len(reason) < MIN_REASON:
        raise SupportError(f"Indique o motivo do acesso (pelo menos {MIN_REASON} caracteres) - fica registado e o gestor vê-o")
    company = await db.get(Company, company_id)
    if company is None:
        raise SupportError("Empresa não encontrada")
    if not company.is_active:
        raise SupportError("Esta empresa está suspensa - reative-a antes de entrar")
    code = secrets.token_urlsafe(24)
    now = _now()
    session = SupportSession(company_id=company.id, admin_user_id=admin.id, reason=reason[:500], started_at=now,
                             expires_at=now + timedelta(minutes=SUPPORT_MINUTES), code_hash=_hash(code),
                             code_expires_at=now + timedelta(seconds=CODE_SECONDS))
    db.add(session)
    await db.commit()
    return {"code": code, "subdomain": company.subdomain, "expires_at": session.expires_at}


def _tokens(session: SupportSession, company: Company) -> tuple[str, str]:
    tenant = company.subdomain if get_settings().is_saas else None
    claims = dict(subject=str(session.admin_user_id), company_id=str(company.id), tenant=tenant,
                  support=str(session.id), expires_at=session.expires_at)
    return (create_access_token(role=UserRole.GESTOR.value, **claims),
            create_refresh_token(role=UserRole.GESTOR.value, **claims))


async def redeem_code(db: AsyncSession, code: str, host_label: str | None) -> tuple[str, str]:
    """The company's address opening the support access: the code, once, within CODE_SECONDS - the session's tokens.
    host_label: SaaS, the subdomain of the address it is opened on (it must be the company's)."""
    session = (await db.execute(select(SupportSession).where(SupportSession.code_hash == _hash(code or "")))).scalar_one_or_none()
    if session is None or session.code_used_at is not None or session.code_expires_at is None \
            or session.code_expires_at < _now() or not is_active(session):
        raise SupportError("Código de suporte inválido ou expirado - volte a entrar a partir de Empresas")
    company = await db.get(Company, session.company_id)
    if get_settings().is_saas and host_label != company.subdomain:
        raise SupportError("Este código abre-se no endereço da empresa")
    session.code_used_at = _now()
    await db.commit()
    return _tokens(session, company)


async def refreshed_access(db: AsyncSession, session_id: str) -> str:
    """A support session's new access token (same end) - refused once it ended or expired."""
    session = await db.get(SupportSession, uuid.UUID(session_id))
    if not is_active(session):
        raise SupportError("O acesso de suporte terminou")
    return _tokens(session, await db.get(Company, session.company_id))[0]


async def support_user(db: AsyncSession, session_id: str, user_id: str) -> tuple[User, SupportSession] | None:
    """The platform user acting in the company as its gestor, for this request only - None when the session ended.
    The user is detached from the database session first: his own account is never changed."""
    session = await db.get(SupportSession, uuid.UUID(session_id))
    if not is_active(session) or str(session.admin_user_id) != user_id:
        return None
    user = (await db.execute(select(User).where(User.id == session.admin_user_id, User.is_active.is_(True),
                                                User.role == UserRole.SUPER_ADMIN))).scalar_one_or_none()
    if user is None:
        return None
    db.expunge(user)
    user.company_id, user.role = session.company_id, UserRole.GESTOR
    user.support_session = session
    return user, session


async def end_support(db: AsyncSession, session_id: uuid.UUID) -> None:
    session = await db.get(SupportSession, session_id)
    if session is not None and session.ended_at is None:
        session.ended_at = _now()
        await db.commit()


async def list_support_sessions(db: AsyncSession, company_id: uuid.UUID, limit: int = 100) -> list[dict]:
    """The company's support accesses, most recent first: who, when, why, until when."""
    rows = (await db.execute(
        select(SupportSession, User.full_name).join(User, User.id == SupportSession.admin_user_id)
        .where(SupportSession.company_id == company_id).order_by(SupportSession.started_at.desc()).limit(limit)
    )).all()
    now = _now()
    return [{"id": str(s.id), "admin_name": name, "reason": s.reason, "started_at": s.started_at,
             "ended_at": s.ended_at or (s.expires_at if s.expires_at <= now else None),
             "active": s.ended_at is None and s.expires_at > now} for s, name in rows]
