"""
Reusable FastAPI dependencies to protect routes.
get_current_user extracts and validates the JWT, loads the user from the DB.
See specification v7, section 2.4 (auth) and 2.5 (multi-tenant isolation).
"""
from app.core.request_context import current_user_id
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token, issued_before
from app.models.user import User
from app.services.permission_service import has_permission
from app.services.support_service import support_user
from app.services.tenant_service import host_claim, request_host


class PortugueseHTTPBearer(HTTPBearer):
    """
    HTTPBearer override - replaces the default English 'Not authenticated'
    message with a PT-PT one, since it reaches the end user directly.
    """
    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials:
        credentials = await super().__call__(request)
        return credentials


bearer_scheme = PortugueseHTTPBearer(
    auto_error=False,
)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates the JWT (type=access) and returns the matching user.
    Use as a Depends() on any route requiring authentication.
    """
    credentials: HTTPAuthorizationCredentials = await bearer_scheme(request)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticacao necessária. Por favor, inicie sessão.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token)

    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada. Por favor, inicie sessão novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # SaaS mode: a session is used only on the address it was opened on (one company's, or the admin one)
    # (an address that is no company's - the bare domain, an IP - accepts no session at all)
    claim = host_claim(request_host(request)) if get_settings().is_saas else None
    if get_settings().is_saas and (claim is None or payload.get("tnt") != claim):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão de outro endereço - inicie sessão neste endereço.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if payload.get("sup"):  # the platform's support access: its user acts in the company as its gestor (support_service)
        found = await support_user(db, payload["sup"], user_id)
        if found is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="O acesso de suporte terminou",
                                headers={"WWW-Authenticate": "Bearer"})
        user = found[0]
        current_user_id.set(user.id)  # what is done is recorded in the platform user's own name
        return user
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilizador não encontrado ou desativado")
    if issued_before(payload, user.password_changed_at):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="A palavra-passe foi alterada - inicie sessão novamente.",
                            headers={"WWW-Authenticate": "Bearer"})

    current_user_id.set(user.id)  # who makes this request: every document it creates records it
    return user


def require_role(*allowed_roles: str):
    """
    Dependency factory - restricts access to specific roles.
    Usage: Depends(require_role('GESTOR', 'ADMIN'))
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Não tem permissão para aceder a este recurso",
            )
        return current_user

    return role_checker


def require_permission(code: str, *, also_allow_roles: tuple[str, ...] = ()):
    """
    Dependency factory - dynamic counterpart to require_role, checking a
    per-company RolePermission grant instead of a hardcoded role tuple. See
    app.services.permission_service for the full design rationale (used by every company-scoped route).
    """
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # Platform-level roles listed in also_allow_roles (e.g. SUPER_ADMIN, which has no
        # company and therefore no grants) pass without a permission lookup.
        if current_user.role.value in also_allow_roles:
            return current_user
        if current_user.company_id is None or not await has_permission(db, current_user.company_id, current_user.role.value, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Não tem permissão para aceder a este recurso",
            )
        return current_user

    return permission_checker
