"""
Pydantic schemas for products.
See specification v6/v7, section 5.1.
Extended (Video 3) with category, brand, image, purchase price, the
managed-by-lote/stock/validade toggles, and richer status.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


def _validate_code(v: str) -> str:
    cleaned = " ".join(v.split())
    if not cleaned:
        raise ValueError("Codigo do produto nao pode estar vazio")
    return cleaned


def _validate_name(v: str) -> str:
    cleaned = " ".join(v.split())
    if not cleaned:
        raise ValueError("Nome do produto nao pode estar vazio")
    return cleaned


class ProductCreateRequest(BaseModel):
    """Request to create a new product."""
    code: str
    name: str
    barcode: str | None = None
    vat_id: uuid.UUID | None = None
    price: float
    min_stock_threshold: float = 0
    expiry_date: date | None = None
    product_type: str = "BEM"
    unit_of_measure_id: uuid.UUID | None = None
    batch_yield: float = 1
    is_raw_material: bool = False

    category_id: uuid.UUID | None = None
    brand: str | None = None
    image_path: str | None = None
    purchase_price: float | None = None
    managed_by_batch: bool = False
    managed_by_stock: bool = True
    managed_by_expiry: bool = False
    not_available_pos: bool = False
    internal_use_only: bool = False
    status: str = "ACTIVO"
    exemption_reason_id: uuid.UUID | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return _validate_code(v)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Preco nao pode ser negativo")
        return v

    @field_validator("purchase_price")
    @classmethod
    def validate_purchase_price(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Preco de compra nao pode ser negativo")
        return v

    @field_validator("min_stock_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Limite minimo de stock nao pode ser negativo")
        return v

    @field_validator("batch_yield")
    @classmethod
    def validate_batch_yield(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Rendimento do lote deve ser maior que zero")
        return v


class ProductUpdateRequest(BaseModel):
    """Request to update a product's editable fields."""
    code: str
    name: str
    barcode: str | None = None
    vat_id: uuid.UUID | None = None
    price: float
    min_stock_threshold: float = 0
    expiry_date: date | None = None
    product_type: str = "BEM"
    unit_of_measure_id: uuid.UUID | None = None
    batch_yield: float = 1
    is_raw_material: bool = False

    category_id: uuid.UUID | None = None
    brand: str | None = None
    image_path: str | None = None
    purchase_price: float | None = None
    managed_by_batch: bool = False
    managed_by_stock: bool = True
    managed_by_expiry: bool = False
    not_available_pos: bool = False
    internal_use_only: bool = False
    status: str = "ACTIVO"
    exemption_reason_id: uuid.UUID | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return _validate_code(v)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Preco nao pode ser negativo")
        return v

    @field_validator("purchase_price")
    @classmethod
    def validate_purchase_price(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Preco de compra nao pode ser negativo")
        return v

    @field_validator("min_stock_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Limite minimo de stock nao pode ser negativo")
        return v

    @field_validator("batch_yield")
    @classmethod
    def validate_batch_yield(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Rendimento do lote deve ser maior que zero")
        return v


class ProductResponse(BaseModel):
    """Product data returned to the client."""
    average_cost: float | None = None  # CMP, computed by the system (read only)
    id: uuid.UUID
    code: str
    name: str
    barcode: str | None
    vat_id: uuid.UUID | None = None
    price: float
    min_stock_threshold: float
    expiry_date: date | None
    product_type: str
    unit_of_measure_id: uuid.UUID | None
    unit_of_measure_code: str | None = None  # attached by the list: the unit's code (UN, CX...)
    sale_units: list[dict] = []  # attached by the list: active sale units (id, code, factor, price, barcode, is_fractional)
    unit_is_fractional: bool = False  # attached by the list: the base unit takes decimal quantities
    batch_yield: float
    is_raw_material: bool
    is_active: bool
    created_at: datetime

    category_id: uuid.UUID | None
    brand: str | None
    image_path: str | None
    purchase_price: float | None
    managed_by_batch: bool
    managed_by_stock: bool
    managed_by_expiry: bool
    not_available_pos: bool
    internal_use_only: bool
    status: str
    exemption_reason_id: uuid.UUID | None

    class Config:
        from_attributes = True