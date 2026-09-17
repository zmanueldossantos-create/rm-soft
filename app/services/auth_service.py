"""
Business logic for phone number authentication.
See specification v7, section 2.4.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.models.user import User, UserRole


class AuthenticationError(Exception):
    """Raised when login fails (wrong phone number or password)."""
    pass


class UserAlreadyExistsError(Exception):
    """Raised when a phone number is already used within the same company."""
    pass


class UserNotFoundError(Exception):
    pass


class PasswordResetNotAllowedError(Exception):
    """Raised when the acting user is not permitted to reset this target user's password."""
    pass


async def create_user(
    db: AsyncSession,
    company_id: uuid.UUID,
    full_name: str,
    phone_number: str,
    password: str,
    role: str,
) -> User:
    """
    Creates a user attached to a Company.
    Created directly by the GESTOR - no public self-registration (section 2.4 v7).
    """
    existing = await db.execute(
        select(User).where(User.company_id == company_id, User.phone_number == phone_number)
    )
    if existing.scalar_one_or_none() is not None:
        raise UserAlreadyExistsError("Ja existe um utilizador registado com este numero de telefone nesta empresa")

    user = User(
        company_id=company_id,
        full_name=full_name,
        phone_number=phone_number,
        password_hash=hash_password(password),
        role=UserRole(role),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, phone_number: str, password: str) -> User:
    """
    Looks up by phone number ALONE (the user does not know their company_id at login time).
    In SaaS mode, the same number can exist under several company_id (section 2.4 v7) -
    all matching accounts are fetched and the password checked against each.
    Phase 1 edge case: if two tenants collide with the same password, the first match wins.
    Acceptable for Phase 1 (SMS verification out of scope).
    """
    result = await db.execute(
        select(User).where(User.phone_number == phone_number, User.is_active == True)
    )
    users = result.scalars().all()
    for user in users:
        if verify_password(password, user.password_hash):
            return user
    raise AuthenticationError("Numero de telefone ou palavra-passe incorretos")


def generate_token_pair(user: User) -> tuple[str, str]:
    """Generates the access token and refresh token for an authenticated user."""
    access_token = create_access_token(
        subject=str(user.id),
        company_id=str(user.company_id),
        role=user.role.value,
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        company_id=str(user.company_id),
    )
    return access_token, refresh_token


async def list_users(db: AsyncSession, company_id: uuid.UUID) -> list[User]:
    """Lists all users belonging to the caller's company (excludes SUPER_ADMIN, which has no company_id)."""
    result = await db.execute(
        select(User).where(User.company_id == company_id).order_by(User.created_at.desc())
    )
    return list(result.scalars().all())


async def toggle_user_status(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, acting_user_id: uuid.UUID) -> User:
    """
    Activates or deactivates a user within the caller's company.
    A GESTOR cannot deactivate their own account (would lock them out).
    """
    if user_id == acting_user_id:
        raise ValueError("Nao pode desativar a sua propria conta")

    result = await db.execute(select(User).where(User.id == user_id, User.company_id == company_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFoundError("Utilizador nao encontrado")

    user.is_active = not user.is_active
    await db.commit()
    await db.refresh(user)
    return user


async def reset_user_password(
    db: AsyncSession,
    target_user_id: uuid.UUID,
    new_password: str,
    acting_user: User,
) -> User:
    """
    Admin-driven password reset (no self-service "forgot password" flow yet
    - no SMS/email infrastructure exists). Scoping:
    - SUPER_ADMIN may reset a GESTOR's password (SUPER_ADMIN created that account).
    - GESTOR may reset their own team's passwords (CAIXA/ARMAZENISTA/CONTABILISTA),
      scoped to their own company - never another GESTOR (only one exists per
      company, created exclusively by SUPER_ADMIN, section 2.4).
    """
    result = await db.execute(select(User).where(User.id == target_user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise UserNotFoundError("Utilizador nao encontrado")

    if acting_user.role == UserRole.SUPER_ADMIN:
        if target.role != UserRole.GESTOR:
            raise PasswordResetNotAllowedError("O SUPER_ADMIN so pode redefinir a palavra-passe do GESTOR")
    elif acting_user.role == UserRole.GESTOR:
        if target.company_id != acting_user.company_id or target.role == UserRole.GESTOR:
            raise PasswordResetNotAllowedError("So pode redefinir a palavra-passe da sua propria equipa")
    else:
        raise PasswordResetNotAllowedError("Sem permissao para redefinir palavras-passe")

    target.password_hash = hash_password(new_password)
    await db.commit()
    await db.refresh(target)
    return target
