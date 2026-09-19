"""
Reusable FastAPI dependencies to protect routes.
get_current_user extracts and validates the JWT, loads the user from the DB.
See specification v7, section 2.4 (auth) and 2.5 (multi-tenant isolation).
"""
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.services.permission_service import has_permission


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
            detail="Autenticacao necessaria. Por favor, inicie sessao.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token)

    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessao invalida ou expirada. Por favor, inicie sessao novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilizador nao encontrado ou desativado")

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
                detail="Nao tem permissao para aceder a este recurso",
            )
        return current_user

    return role_checker


def require_permission(code: str):
    """
    Dependency factory - dynamic counterpart to require_role, checking a
    per-company RolePermission grant instead of a hardcoded role tuple. See
    app.services.permission_service for the full design rationale (pilot
    scope: only Consumo Interno's routes use this for now).
    """
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.company_id is None or not await has_permission(db, current_user.company_id, current_user.role.value, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nao tem permissao para aceder a este recurso",
            )
        return current_user

    return permission_checker
