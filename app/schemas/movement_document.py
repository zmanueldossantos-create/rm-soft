"""
Pydantic schemas for StockMovementDocument (Entrada/Saida) - see PARTIE1&2 GESTAO DE STOCK.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class MovementDocumentLineRequest(BaseModel):
    product_id: uuid.UUID
    quantity: float
    sale_unit_id: uuid.UUID | None = None  # entered in one of the product's units (SC...); empty = its base unit
    purchase_price: float = 0
    sale_price: float = 0


class MovementDocumentCreateRequest(BaseModel):
    movement_type_id: uuid.UUID
    warehouse_id: uuid.UUID
    movement_date: date | None = None
    description: str | None = None
    supplier_id: uuid.UUID | None = None
    lines: list[MovementDocumentLineRequest]

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list) -> list:
        if not v:
            raise ValueError("O movimento deve ter pelo menos uma linha")
        return v


class MovementDocumentLineResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_code_snapshot: str
    product_name_snapshot: str
    unit_snapshot: str | None
    sale_unit_id: uuid.UUID | None = None
    unit_factor: float = 1
    quantity: float
    purchase_price: float
    sale_price: float
    line_total: float

    class Config:
        from_attributes = True


class MovementDocumentResponse(BaseModel):
    id: uuid.UUID
    movement_type_id: uuid.UUID
    warehouse_id: uuid.UUID
    supplier_id: uuid.UUID | None
    series: str
    number: int
    movement_date: date
    description: str | None
    total_quantity: float
    total_value: float
    created_at: datetime

    class Config:
        from_attributes = True


class MovementDocumentDetailResponse(MovementDocumentResponse):
    lines: list[MovementDocumentLineResponse]
