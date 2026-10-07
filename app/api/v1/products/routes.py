"""
Product routes - scoped to the caller's company (multi-tenant isolation, section 2.5 v7).
Accessible to GESTOR/ADMIN of the company - not restricted to SUPER_ADMIN,
since each business manages its own catalog (see decision on SUPER_ADMIN scope).
"""
import uuid

import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.schemas.product_sale_unit import ProductSaleUnitRequest, ProductSaleUnitResponse
from app.services.product_sale_unit_service import (
    SaleUnitInvalidError, SaleUnitNeedsConfirmationError, SaleUnitNotFoundError, create_sale_unit, list_sale_units, toggle_sale_unit, update_sale_unit,
)
from app.models.user import User
from app.schemas.product import ProductCreateRequest, ProductUpdateRequest, ProductResponse
from app.schemas.recipe import RecipeSetRequest, RecipeIngredientResponse
from app.services.recipe_service import (
    get_recipe,
    set_recipe,
    list_products_with_recipe,
    ProductNotFoundError as RecipeProductNotFoundError,
    InvalidRecipeError,
)
from app.models.product import Product
from app.services.product_service import get_product_or_raise
from sqlalchemy import select as sa_select
from app.services.product_service import (
    create_product,
    list_products,
    update_product,
    toggle_product_status,
    ProductAlreadyExistsError,
    ProductNotFoundError,
    ExemptionReasonRequiredError,
)

router = APIRouter(prefix="/api/v1/products", tags=["products"])



@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_new_product(
    payload: ProductCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    """Creates a product within the caller's company."""
    try:
        product = await create_product(
            db,
            company_id=current_user.company_id,
            code=payload.code,
            name=payload.name,
            barcode=payload.barcode,
            vat_id=payload.vat_id,
            price=payload.price,
            min_stock_threshold=payload.min_stock_threshold,
            expiry_date=payload.expiry_date,
            product_type=payload.product_type,
            unit_of_measure_id=payload.unit_of_measure_id,
            is_raw_material=payload.is_raw_material,
            category_id=payload.category_id,
            brand=payload.brand,
            image_path=payload.image_path,
            purchase_price=payload.purchase_price,
            managed_by_batch=payload.managed_by_batch,
            managed_by_stock=payload.managed_by_stock,
            managed_by_expiry=payload.managed_by_expiry,
            not_available_pos=payload.not_available_pos,
            prepared_in_kitchen=payload.prepared_in_kitchen,
            internal_use_only=payload.internal_use_only,
            status=payload.status,
            exemption_reason_id=payload.exemption_reason_id,
        )
    except ProductAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ExemptionReasonRequiredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return product


@router.get("", response_model=list[ProductResponse])
async def get_products(
    db: AsyncSession = Depends(get_db),
    # CAIXA needs read access too - a cashier must see the product catalog to sell
    # (Caixa, Contas Abertas). ARMAZENISTA needs it too - Consumo Interno's product
    # picker calls this same list. Only GESTOR can create/edit products.
    current_user: User = Depends(require_permission("products:view")),
):
    """Lists all products belonging to the caller's company."""
    return await list_products(db, current_user.company_id)


@router.patch("/{product_id}", response_model=ProductResponse)
async def edit_product(
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    """Updates a product's editable fields, scoped to the caller's company."""
    try:
        product = await update_product(
            db,
            company_id=current_user.company_id,
            product_id=product_id,
            code=payload.code,
            name=payload.name,
            barcode=payload.barcode,
            vat_id=payload.vat_id,
            price=payload.price,
            min_stock_threshold=payload.min_stock_threshold,
            expiry_date=payload.expiry_date,
            product_type=payload.product_type,
            unit_of_measure_id=payload.unit_of_measure_id,
            is_raw_material=payload.is_raw_material,
            category_id=payload.category_id,
            brand=payload.brand,
            purchase_price=payload.purchase_price,
            managed_by_batch=payload.managed_by_batch,
            managed_by_stock=payload.managed_by_stock,
            managed_by_expiry=payload.managed_by_expiry,
            not_available_pos=payload.not_available_pos,
            prepared_in_kitchen=payload.prepared_in_kitchen,
            internal_use_only=payload.internal_use_only,
            status=payload.status,
            exemption_reason_id=payload.exemption_reason_id,
        )
    except ProductAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return product


@router.patch("/{product_id}/toggle-status", response_model=ProductResponse)
async def toggle_status(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    """Activates or deactivates a product."""
    try:
        product = await toggle_product_status(db, current_user.company_id, product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return product


@router.get("/{product_id}/recipe", response_model=list[RecipeIngredientResponse])
async def get_product_recipe(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("recipes:view")),
):
    """Lists the ingredients (Bill of Materials) for a finished product."""
    return await get_recipe(db, current_user.company_id, product_id)


@router.put("/{product_id}/recipe", response_model=list[RecipeIngredientResponse])
async def put_product_recipe(
    product_id: uuid.UUID,
    payload: RecipeSetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("recipes:manage")),
):
    """Replaces the finished product's entire recipe with the given ingredients."""
    try:
        return await set_recipe(
            db, current_user.company_id, product_id, payload.batch_yield,
            [{"ingredient_product_id": i.ingredient_product_id, "quantity_per_batch": i.quantity_per_batch, "sale_unit_id": i.sale_unit_id}
             for i in payload.ingredients],
            batch_yield_sale_unit_id=payload.batch_yield_sale_unit_id,
        )
    except RecipeProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidRecipeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/with-recipe", response_model=list[ProductResponse])
async def get_products_with_recipe(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("recipes:list")),
):
    """Lists the products that currently have a recipe defined - i.e. can be produced."""
    ids = await list_products_with_recipe(db, current_user.company_id)
    if not ids:
        return []
    result = await db.execute(sa_select(Product).where(Product.id.in_(ids)))
    return list(result.scalars().all())


ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB


@router.post("/{product_id}/image", response_model=ProductResponse)
async def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    """Uploads/replaces a product's image. Stored locally (Phase 1), same pattern as the company logo."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Formato de imagem invalido - use PNG, JPG ou WEBP")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Imagem demasiado grande - maximo 2MB")

    try:
        product = await get_product_or_raise(db, current_user.company_id, product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    for existing_ext in ALLOWED_IMAGE_EXTENSIONS:
        old_path = os.path.join("uploads", "products", f"{product.id}{existing_ext}")
        if os.path.exists(old_path):
            os.remove(old_path)

    os.makedirs(os.path.join("uploads", "products"), exist_ok=True)
    filename = f"{product.id}{ext}"
    filepath = os.path.join("uploads", "products", filename)
    with open(filepath, "wb") as f:
        f.write(contents)

    product.image_path = f"/uploads/products/{filename}"
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}/image", response_model=ProductResponse)
async def delete_product_image(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    """Removes a product's image - deletes the file on disk and clears image_path."""
    try:
        product = await get_product_or_raise(db, current_user.company_id, product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    for existing_ext in ALLOWED_IMAGE_EXTENSIONS:
        old_path = os.path.join("uploads", "products", f"{product.id}{existing_ext}")
        if os.path.exists(old_path):
            os.remove(old_path)

    product.image_path = None
    await db.commit()
    await db.refresh(product)
    return product


# ---------- Sale units (pallet / egg, box / blister / tablet) ----------

def _sale_unit_error(e: Exception):
    if isinstance(e, SaleUnitNeedsConfirmationError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": "Confirme para guardar", "warnings": e.warnings})
    if isinstance(e, SaleUnitNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/{product_id}/sale-units", response_model=list[ProductSaleUnitResponse])
async def get_sale_units(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:view")),
):
    try:
        return await list_sale_units(db, current_user.company_id, product_id)
    except (SaleUnitNotFoundError, SaleUnitInvalidError, SaleUnitNeedsConfirmationError) as e:
        _sale_unit_error(e)


@router.post("/{product_id}/sale-units", response_model=ProductSaleUnitResponse, status_code=status.HTTP_201_CREATED)
async def post_sale_unit(
    product_id: uuid.UUID,
    payload: ProductSaleUnitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    try:
        return await create_sale_unit(db, current_user.company_id, product_id, payload.unit_of_measure_id, payload.factor, payload.price, payload.barcode, payload.confirm)
    except (SaleUnitNotFoundError, SaleUnitInvalidError, SaleUnitNeedsConfirmationError) as e:
        _sale_unit_error(e)


@router.patch("/{product_id}/sale-units/{unit_id}", response_model=ProductSaleUnitResponse)
async def patch_sale_unit(
    product_id: uuid.UUID,
    unit_id: uuid.UUID,
    payload: ProductSaleUnitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    try:
        return await update_sale_unit(db, current_user.company_id, product_id, unit_id, payload.unit_of_measure_id, payload.factor, payload.price, payload.barcode, payload.confirm)
    except (SaleUnitNotFoundError, SaleUnitInvalidError, SaleUnitNeedsConfirmationError) as e:
        _sale_unit_error(e)


@router.patch("/{product_id}/sale-units/{unit_id}/toggle-status", response_model=ProductSaleUnitResponse)
async def patch_sale_unit_status(
    product_id: uuid.UUID,
    unit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    try:
        return await toggle_sale_unit(db, current_user.company_id, product_id, unit_id)
    except (SaleUnitNotFoundError, SaleUnitInvalidError, SaleUnitNeedsConfirmationError) as e:
        _sale_unit_error(e)
