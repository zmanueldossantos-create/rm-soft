"""
ProductCategory routes - scoped to the caller's company (Video 3).
Managed by GESTOR only, unlike platform-wide catalogs (SUPER_ADMIN).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.product_category import ProductCategoryRequest, ProductCategoryResponse
from app.services.product_category_service import (
    list_product_categories,
    create_product_category,
    update_product_category,
    toggle_product_category,
    ProductCategoryNotFoundError,
    ProductCategoryAlreadyExistsError,
)

router = APIRouter(prefix="/api/v1/product-categories", tags=["product-categories"])


@router.get("", response_model=list[ProductCategoryResponse])
async def get_product_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("product_categories:view")),
):
    return await list_product_categories(db, current_user.company_id)


@router.post("", response_model=ProductCategoryResponse, status_code=status.HTTP_201_CREATED)
async def post_product_category(
    payload: ProductCategoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("product_categories:manage")),
):
    try:
        return await create_product_category(
            db, current_user.company_id, payload.name,
            payload.not_available_purchases, payload.not_available_pos, payload.not_available_sales,
        )
    except ProductCategoryAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/{category_id}", response_model=ProductCategoryResponse)
async def patch_product_category(
    category_id: uuid.UUID,
    payload: ProductCategoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("product_categories:manage")),
):
    try:
        return await update_product_category(
            db, current_user.company_id, category_id, payload.name,
            payload.not_available_purchases, payload.not_available_pos, payload.not_available_sales,
        )
    except ProductCategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ProductCategoryAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/{category_id}/toggle-status", response_model=ProductCategoryResponse)
async def toggle_product_category_status(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("product_categories:manage")),
):
    try:
        return await toggle_product_category(db, current_user.company_id, category_id)
    except ProductCategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
