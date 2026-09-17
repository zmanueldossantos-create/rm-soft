"""
Business logic for RecipeIngredient (Bill of Materials) - defines which
ingredients a finished product's recipe consumes PER BATCH, and how many
units of the finished product one batch yields (see Product.batch_yield).
Generic to any product - not specific to bread or any single business type.
"""
import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recipe_ingredient import RecipeIngredient
from app.models.product import Product


class ProductNotFoundError(Exception):
    pass


class InvalidRecipeError(Exception):
    """Raised for self-referencing ingredients or an ingredient that doesn't belong to the company."""
    pass


async def _check_product_exists(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> None:
    result = await db.execute(select(Product).where(Product.id == product_id, Product.company_id == company_id))
    if result.scalar_one_or_none() is None:
        raise ProductNotFoundError("Produto nao encontrado")


async def get_recipe(db: AsyncSession, company_id: uuid.UUID, finished_product_id: uuid.UUID) -> list[RecipeIngredient]:
    result = await db.execute(
        select(RecipeIngredient)
        .where(RecipeIngredient.company_id == company_id, RecipeIngredient.finished_product_id == finished_product_id)
    )
    return list(result.scalars().all())


async def list_products_with_recipe(db: AsyncSession, company_id: uuid.UUID) -> list[uuid.UUID]:
    """Returns the ids of every product that currently has at least one recipe ingredient defined."""
    result = await db.execute(
        select(RecipeIngredient.finished_product_id)
        .where(RecipeIngredient.company_id == company_id)
        .distinct()
    )
    return [row[0] for row in result.all()]


async def set_recipe(
    db: AsyncSession,
    company_id: uuid.UUID,
    finished_product_id: uuid.UUID,
    batch_yield: float,
    ingredients: list[dict],  # [{"ingredient_product_id": UUID, "quantity_per_batch": float}, ...]
) -> list[RecipeIngredient]:
    """
    Replaces the finished product's entire recipe (ingredients per batch,
    plus how many units one batch yields) with exactly this set - simplest
    mental model for GESTOR (edit the whole recipe at once).
    """
    await _check_product_exists(db, company_id, finished_product_id)

    seen_ingredient_ids = set()
    for ing in ingredients:
        if ing["ingredient_product_id"] == finished_product_id:
            raise InvalidRecipeError("Um produto nao pode ser ingrediente de si mesmo")
        if ing["ingredient_product_id"] in seen_ingredient_ids:
            raise InvalidRecipeError("O mesmo ingrediente nao pode aparecer duas vezes na receita")
        seen_ingredient_ids.add(ing["ingredient_product_id"])
        await _check_product_exists(db, company_id, ing["ingredient_product_id"])

    product_result = await db.execute(select(Product).where(Product.id == finished_product_id))
    product = product_result.scalar_one()
    product.batch_yield = batch_yield

    await db.execute(
        delete(RecipeIngredient).where(
            RecipeIngredient.company_id == company_id,
            RecipeIngredient.finished_product_id == finished_product_id,
        )
    )

    rows = []
    for ing in ingredients:
        row = RecipeIngredient(
            company_id=company_id,
            finished_product_id=finished_product_id,
            ingredient_product_id=ing["ingredient_product_id"],
            quantity_per_batch=ing["quantity_per_batch"],
        )
        db.add(row)
        rows.append(row)

    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows