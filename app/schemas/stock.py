"""
Pydantic schemas for stock management.
See specification v6/v7, section 5.1.
Multi-warehouse (see stock_service module docstring): every request that
touches a specific warehouse (adjust, transfer, loss, levels, movements)
carries a warehouse_id, receptions included: they go through movement documents,
which name their warehouse explicitly.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class StockLevelResponse(BaseModel):
    product_id: uuid.UUID
    product_code: str
    product_name: str
    quantity: float
    min_stock_threshold: float
    is_low: bool
    followed_by_lot: bool = False  # followed by lot / expiry: its lots are listed (Stock > Lotes)
    expired_quantity: float = 0  # in expired lots - never sold
    location_id: uuid.UUID | None = None  # emplacements (optional): where it is kept in this warehouse
    location_code: str | None = None
    active_substance: str | None = None  # Farmácia: a medicine is found by its substance (DCI)


class StockAdjustRequest(BaseModel):
    sale_unit_id: uuid.UUID | None = None  # quantity entered in one of the product's units; empty = base unit
    fiscal_period_id: uuid.UUID | None = None  # internal entry: the active or the soft-closed period; empty = the active one
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    new_quantity: float
    reason: str
    # a product followed by lot / expiry: a decrease takes lot_id (empty = FEFO), an increase fills lot_number / expiry_date
    lot_id: uuid.UUID | None = None
    lot_number: str | None = None
    expiry_date: date | None = None

    @field_validator("new_quantity")
    @classmethod
    def validate_new_quantity(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Quantidade não pode ser negativa")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 5:
            raise ValueError("Motivo obrigatório - mínimo 5 caracteres")
        return cleaned


class StockTransferRequest(BaseModel):
    sale_unit_id: uuid.UUID | None = None  # quantity entered in one of the product's units; empty = base unit
    fiscal_period_id: uuid.UUID | None = None  # internal entry: the active or the soft-closed period; empty = the active one
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity: float
    reason: str | None = None
    lot_id: uuid.UUID | None = None  # a product followed by lot: the lot moved (empty = FEFO, never an expired one)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        return v


class StockLossRequest(BaseModel):
    sale_unit_id: uuid.UUID | None = None  # quantity entered in one of the product's units; empty = base unit
    fiscal_period_id: uuid.UUID | None = None  # internal entry: the active or the soft-closed period; empty = the active one
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity: float
    loss_category: str
    reason: str | None = None
    lot_id: uuid.UUID | None = None  # a product followed by lot: the lot lost (empty = FEFO, the expired first)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        return v

    @field_validator("loss_category")
    @classmethod
    def validate_loss_category(cls, v: str) -> str:
        allowed = {"EXPIRACAO", "QUEBRA", "ROUBO", "OUTRO"}
        if v not in allowed:
            raise ValueError(f"Categoria inválida - deve ser uma de: {', '.join(sorted(allowed))}")
        return v


class StockMovementResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    movement_type: str
    quantity: float
    loss_category: str | None
    counterpart_warehouse_id: uuid.UUID | None
    is_transfer_source: bool | None
    is_production_output: bool | None
    reason: str | None
    reference: str | None
    created_at: datetime
    lots: str | None = None  # a product followed by lot: the lots this row moved (L1 · 2, L2 · 1)

    class Config:
        from_attributes = True
