"""
Business logic for ProductCategory - company-scoped catalog (Video 3),
managed by the company's own GESTOR (not SUPER_ADMIN, unlike the
platform-wide catalogs in Configuracoes).
"""
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_category import ProductCategory


class ProductCategoryNotFoundError(Exception):
    pass


class ProductCategoryAlreadyExistsError(Exception):
    pass


async def _check_name_available(db: AsyncSession, company_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None) -> None:
    query = select(ProductCategory).where(ProductCategory.company_id == company_id, func.lower(ProductCategory.name) == name.lower())
    if exclude_id is not None:
        query = query.where(ProductCategory.id != exclude_id)
    if (await db.execute(query)).scalar_one_or_none() is not None:
        raise ProductCategoryAlreadyExistsError("Ja existe uma categoria com este nome")


async def list_product_categories(db: AsyncSession, company_id: uuid.UUID) -> list[ProductCategory]:
    result = await db.execute(
        select(ProductCategory).where(ProductCategory.company_id == company_id).order_by(ProductCategory.name)
    )
    return list(result.scalars().all())


async def create_product_category(
    db: AsyncSession, company_id: uuid.UUID, name: str,
    not_available_purchases: bool = False, not_available_pos: bool = False, not_available_sales: bool = False,
) -> ProductCategory:
    await _check_name_available(db, company_id, name)
    category = ProductCategory(
        company_id=company_id, name=name,
        not_available_purchases=not_available_purchases,
        not_available_pos=not_available_pos,
        not_available_sales=not_available_sales,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def update_product_category(
    db: AsyncSession, company_id: uuid.UUID, category_id: uuid.UUID, name: str,
    not_available_purchases: bool = False, not_available_pos: bool = False, not_available_sales: bool = False,
) -> ProductCategory:
    result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_id, ProductCategory.company_id == company_id))
    category = result.scalar_one_or_none()
    if category is None:
        raise ProductCategoryNotFoundError("Categoria de produto nao encontrada")
    await _check_name_available(db, company_id, name, exclude_id=category_id)
    category.name = name
    category.not_available_purchases = not_available_purchases
    category.not_available_pos = not_available_pos
    category.not_available_sales = not_available_sales
    await db.commit()
    await db.refresh(category)
    return category


async def toggle_product_category(db: AsyncSession, company_id: uuid.UUID, category_id: uuid.UUID) -> ProductCategory:
    result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_id, ProductCategory.company_id == company_id))
    category = result.scalar_one_or_none()
    if category is None:
        raise ProductCategoryNotFoundError("Categoria de produto nao encontrada")
    category.is_active = not category.is_active
    await db.commit()
    await db.refresh(category)
    return category
