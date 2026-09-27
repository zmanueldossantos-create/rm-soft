"""
Phone number authentication routes.
See specification v7, section 2.4.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    UserAlreadyExistsError,
    UserNotFoundError,
    PasswordResetNotAllowedError,
)
from app.api.deps import get_current_user, require_role
from app.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(payload: PhoneLoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with phone number + password."""
    try:
        user = await authenticate_user(db, payload.phone_number, payload.password)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    access_token, refresh_token = generate_token_pair(user)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest):
    """Refreshes the access token from a valid refresh token."""
    data = decode_token(payload.refresh_token)
    if data is None or data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao invalida ou expirada. Por favor, inicie sessao novamente.")
    new_access_token = create_access_token(subject=data["sub"], company_id=data["company_id"], role=data.get("role", ""))
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
