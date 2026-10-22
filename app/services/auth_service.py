"""
Business logic for phone number authentication.
See specification v7, section 2.4.
"""
import uuid
from datetime import datetime, timezone

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
        raise UserAlreadyExistsError("Já existe um utilizador registado com este número de telefone nesta empresa")
    from app.services.plan_service import check_limit
    await check_limit(db, company_id, "max_users")

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


async def update_user(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    full_name: str,
    phone_number: str,
    role: str,
) -> User:
    """Edits an existing user's name, phone and role - restricted to the GESTOR of their
    company. The phone uniqueness check excludes the user's own current row."""
    result = await db.execute(select(User).where(User.id == user_id, User.company_id == company_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFoundError("Utilizador não encontrado")

    existing = await db.execute(
        select(User).where(User.company_id == company_id, User.phone_number == phone_number, User.id != user_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise UserAlreadyExistsError("Já existe um utilizador registado com este número de telefone nesta empresa")

    user.full_name = full_name
    user.phone_number = phone_number
    user.role = UserRole(role)
    await db.commit()
    await db.refresh(user)
    return user


PLATFORM = "PLATFORM"  # authenticate_user scope: the platform's accounts only (SUPER_ADMIN, no company)


async def authenticate_user(db: AsyncSession, phone_number: str, password: str,
                            scope: uuid.UUID | str | None = None) -> User:
    """
    Looks up the active accounts with this phone number and checks the password against each.
    scope: None = every account (local mode: one company per installation); a company_id = that company's accounts
    only (SaaS mode: the company is known from its address, so the same number in another company never interferes);
    PLATFORM = the platform's accounts (the admin address).
    """
    query = select(User).where(User.phone_number == phone_number, User.is_active == True)  # noqa: E712
    if scope == PLATFORM:
        query = query.where(User.company_id.is_(None))
    elif scope is not None:
        query = query.where(User.company_id == scope)
    users = (await db.execute(query)).scalars().all()
    for user in users:
        if verify_password(password, user.password_hash):
            return user
    raise AuthenticationError("Número de telefone ou palavra-passe incorretos")


class PasswordChangeError(Exception):
    """Raised when a user's own password change is refused (wrong current password, same password)."""


async def change_own_password(db: AsyncSession, user: User, current_password: str, new_password: str) -> None:
    """The user changes their own password: the current one proves it is them. Every other session of the account
    ends (password_changed_at); the caller issues this device a new one."""
    if not verify_password(current_password, user.password_hash):
        raise PasswordChangeError("A palavra-passe atual está incorreta")
    if verify_password(new_password, user.password_hash):
        raise PasswordChangeError("A nova palavra-passe tem de ser diferente da atual")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    await db.commit()


def generate_token_pair(user: User, tenant: str | None = None) -> tuple[str, str]:
    """Generates the access token and refresh token for an authenticated user (tenant: SaaS mode, the address)."""
    access_token = create_access_token(
        subject=str(user.id),
        company_id=str(user.company_id),
        role=user.role.value,
        tenant=tenant,
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        company_id=str(user.company_id),
        role=user.role.value,
        tenant=tenant,
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
        raise ValueError("Não pode desativar a sua propria conta")

    result = await db.execute(select(User).where(User.id == user_id, User.company_id == company_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFoundError("Utilizador não encontrado")
    if not user.is_active:  # switched back on: one more active user
        from app.services.plan_service import check_limit
        await check_limit(db, company_id, "max_users")

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
        raise UserNotFoundError("Utilizador não encontrado")

    if acting_user.role == UserRole.SUPER_ADMIN:
        if target.role != UserRole.GESTOR:
            raise PasswordResetNotAllowedError("O SUPER_ADMIN só pode redefinir a palavra-passe do GESTOR")
    elif acting_user.role == UserRole.GESTOR:
        if target.company_id != acting_user.company_id or target.role == UserRole.GESTOR:
            raise PasswordResetNotAllowedError("So pode redefinir a palavra-passe da sua propria equipa")
    else:
        raise PasswordResetNotAllowedError("Sem permissão para redefinir palavras-passe")

    target.password_hash = hash_password(new_password)
    target.password_changed_at = datetime.now(timezone.utc)  # the account's open sessions end
    await db.commit()
    await db.refresh(target)
    return target
