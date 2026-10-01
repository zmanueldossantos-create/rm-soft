"""
Pydantic schemas for RecipeIngredient (Bill of Materials) and production.
Recipes are expressed PER BATCH (see Product.batch_yield) rather than per
single unit - e.g. "1 saco de farinha per batch -> 400 paes" - matching
how production is actually measured and avoiding error-prone tiny decimals.
"""
import uuid

from pydantic import BaseModel, field_validator


class RecipeIngredientInput(BaseModel):
    ingredient_product_id: uuid.UUID
    quantity_per_batch: float

    @field_validator("quantity_per_batch")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantidade por lote deve ser maior que zero")
        return v


class RecipeSetRequest(BaseModel):
    batch_yield: float
    ingredients: list[RecipeIngredientInput]

    @field_validator("batch_yield")
    @classmethod
    def validate_batch_yield(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Rendimento do lote deve ser maior que zero")
        return v


class RecipeIngredientResponse(BaseModel):
    id: uuid.UUID
    ingredient_product_id: uuid.UUID
    quantity_per_batch: float

    class Config:
        from_attributes = True


class ProductionEstimateIngredient(BaseModel):
    ingredient_product_id: uuid.UUID
    available: float
    quantity_per_batch: float


class ProductionEstimateResponse(BaseModel):
    max_units: int
    bottleneck_product_id: uuid.UUID | None
    ingredients: list[ProductionEstimateIngredient]


class ProduceStockRequest(BaseModel):
    fiscal_period_id: uuid.UUID | None = None  # internal entry: the active or the soft-closed period; empty = the active one
    warehouse_id: uuid.UUID
    finished_product_id: uuid.UUID
    quantity_to_produce: float
    reason: str | None = None

    @field_validator("quantity_to_produce")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantidade a produzir deve ser maior que zero")
        return v