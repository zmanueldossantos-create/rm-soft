"""
Pydantic schemas for stock management.
See specification v6/v7, section 5.1.
Multi-warehouse (see stock_service module docstring): every request that
touches a specific warehouse (adjust, transfer, loss, levels, movements)
carries a warehouse_id - receive_stock always targets the CENTRAL
warehouse implicitly (goods are always received centrally).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class StockLevelResponse(BaseModel):
    product_id: uuid.UUID
    product_code: str
    product_name: str
    quantity: float
    min_stock_threshold: float
    is_low: bool


class StockReceiveRequest(BaseModel):
    fiscal_period_id: uuid.UUID | None = None  # internal entry: the active or the soft-closed period; empty = the active one
    product_id: uuid.UUID
    quantity: float
    reason: str | None = None

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        return v


class StockAdjustRequest(BaseModel):
    fiscal_period_id: uuid.UUID | None = None  # internal entry: the active or the soft-closed period; empty = the active one
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    new_quantity: float
    reason: str

    @field_validator("new_quantity")
    @classmethod
    def validate_new_quantity(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Quantidade nao pode ser negativa")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 5:
            raise ValueError("Motivo obrigatorio - minimo 5 caracteres")
        return cleaned


class StockTransferRequest(BaseModel):
    fiscal_period_id: uuid.UUID | None = None  # internal entry: the active or the soft-closed period; empty = the active one
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity: float
    reason: str | None = None

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        return v


class StockLossRequest(BaseModel):
    fiscal_period_id: uuid.UUID | None = None  # internal entry: the active or the soft-closed period; empty = the active one
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity: float
    loss_category: str
    reason: str | None = None

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
            raise ValueError(f"Categoria invalida - deve ser uma de: {', '.join(sorted(allowed))}")
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

    class Config:
        from_attributes = True
