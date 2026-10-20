"""
Phone number authentication routes.
See specification v7, section 2.4.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.company import Company
from app.core.security import decode_token, create_access_token
from app.schemas.auth import PhoneLoginRequest, TokenPair, RefreshRequest, UserCreateRequest, UserUpdateRequest, UserResponse, PasswordResetRequest
from app.services.auth_service import (
    authenticate_user,
    generate_token_pair,
    create_user,
    update_user,
    list_users,
    toggle_user_status,
    reset_user_password,
    AuthenticationError,
    PLATFORM,
    UserAlreadyExistsError,
    UserNotFoundError,
    PasswordResetNotAllowedError,
)
from app.api.deps import get_current_user, require_role
from app.models.user import User
from app.services.tenant_service import domain_allowed, host_claim, request_host, resolve_tenant, tenant_claim

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def _login_scope(db: AsyncSession, request: Request):
    """SaaS mode: whose accounts this address knows (a company's, or the platform's), and the session's claim. Refuses
    an address that is no company's, or a suspended company's. Local mode: every account, no claim."""
    settings = get_settings()
    if not settings.is_saas:
        return None, None
    tenant = await resolve_tenant(db, request_host(request))
    if tenant.kind == "admin":
        return PLATFORM, tenant_claim(tenant)
    if tenant.kind == "none":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Abra o endereço da sua empresa (ex.: nome-da-empresa.{settings.BASE_DOMAIN})")
    if tenant.company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Endereço desconhecido - verifique o endereço da sua empresa")
    if not tenant.company.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Esta empresa está suspensa - contacte a RM SOFT")
    return tenant.company.id, tenant_claim(tenant)


@router.get("/domain-check")
async def domain_check(domain: str = "", db: AsyncSession = Depends(get_db)):
    """Public, for the HTTPS proxy (Caddy on-demand certificates): 200 for the admin address and an active company's,
    404 otherwise - so no certificate is ever requested for an invented address."""
    if not await domain_allowed(db, domain):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endereço desconhecido")
    return {"ok": True}


@router.get("/tenant")
async def get_tenant(request: Request, db: AsyncSession = Depends(get_db)):
    """Public (before the login): whose login screen this is - the company's name and logo, the platform, or (SaaS mode)
    no company at this address."""
    settings = get_settings()
    base = {"mode": settings.DEPLOYMENT_MODE, "base_domain": settings.BASE_DOMAIN}
    if not settings.is_saas:
        # an installation has one company: its name on the login; with several (a development machine), none of them
        active = (await db.execute(select(Company).where(Company.is_active.is_(True)).limit(2))).scalars().all()
        company = active[0] if len(active) == 1 else None
        return {**base, "kind": "company" if company else "platform", "name": (company.short_name or company.name) if company else None,
                "logo_path": company.logo_path if company else None, "active": True}
    tenant = await resolve_tenant(db, request_host(request))
    if tenant.kind == "admin":
        return {**base, "kind": "admin", "name": "Administração RM SOFT", "logo_path": None, "active": True}
    if tenant.kind == "none" or tenant.company is None:
        return {**base, "kind": "none", "name": None, "logo_path": None, "active": False}
    company = tenant.company
    return {**base, "kind": "company", "name": company.short_name or company.name, "logo_path": company.logo_path,
            "active": company.is_active}


@router.post("/login", response_model=TokenPair)
async def login(payload: PhoneLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Login with phone number + password - in SaaS mode, among the accounts of the address's company only."""
    scope, claim = await _login_scope(db, request)
    try:
        user = await authenticate_user(db, payload.phone_number, payload.password, scope=scope)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    access_token, refresh_token = generate_token_pair(user, tenant=claim)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Refreshes the access token from a valid refresh token - in SaaS mode, only on the address it was issued for."""
    data = decode_token(payload.refresh_token)
    if data is None or data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida ou expirada. Por favor, inicie sessão novamente.")
    claim = host_claim(request_host(request)) if get_settings().is_saas else None
    if get_settings().is_saas and (claim is None or data.get("tnt") != claim):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão de outro endereço - inicie sessão neste endereço.")
    if get_settings().is_saas and data.get("company_id") not in (None, "None"):
        company = await db.get(Company, uuid.UUID(data["company_id"]))
        if company is None or not company.is_active:  # a suspended company: its sessions end at the next refresh
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Esta empresa está suspensa - contacte a RM SOFT")
    new_access_token = create_access_token(subject=data["sub"], company_id=data["company_id"], role=data.get("role", ""),
                                           tenant=data.get("tnt"))
    return TokenPair(access_token=new_access_token, refresh_token=payload.refresh_token)


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user from the token."""
    return {
        "id": str(current_user.id),
        "full_name": current_user.full_name,
        "phone_number": current_user.phone_number,
        "role": current_user.role.value,
        "company_id": str(current_user.company_id) if current_user.company_id else None,
    }


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_new_user(
    payload: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    """
    Creates a user - restricted to the GESTOR of the caller's company.
    company_id is derived from the caller's token, never supplied by the client
    (prevents creating a user in another company - section 2.5 v7).
    """
    try:
        user = await create_user(
            db,
            company_id=current_user.company_id,
            full_name=payload.full_name,
            phone_number=payload.phone_number,
            password=payload.password,
            role=payload.role,
        )
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def edit_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    """Edits an existing user - restricted to the GESTOR of the caller's company."""
    try:
        user = await update_user(
            db,
            company_id=current_user.company_id,
            user_id=user_id,
            full_name=payload.full_name,
            phone_number=payload.phone_number,
            role=payload.role,
        )
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return user


@router.get("/users", response_model=list[UserResponse])
async def get_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    """Lists all users belonging to the caller's company."""
    return await list_users(db, current_user.company_id)


@router.patch("/users/{user_id}/toggle-status", response_model=UserResponse)
async def toggle_status(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    """Activates or deactivates a user."""
    try:
        user = await toggle_user_status(db, current_user.company_id, user_id, current_user.id)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return user


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
async def reset_password(
    user_id: uuid.UUID,
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN", "GESTOR")),
):
    """
    Admin-driven password reset - no self-service "forgot password" flow
    yet. SUPER_ADMIN may reset a GESTOR's password; GESTOR may reset their
    own team's passwords (never another GESTOR). Scope is enforced in
    reset_user_password.
    """
    try:
        return await reset_user_password(db, user_id, payload.new_password, current_user)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PasswordResetNotAllowedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
