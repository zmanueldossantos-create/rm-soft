import uuid

from pydantic import BaseModel, field_validator


class ProductSaleUnitRequest(BaseModel):
    unit_of_measure_id: uuid.UUID
    factor: float
    price: float
    price_2: float | None = None  # «Preço 2» / «Preço 3» of this unit: empty = not offered
    price_3: float | None = None
    barcode: str | None = None
    confirm: bool = False  # the user confirmed the warnings returned by a first attempt

    @field_validator("factor")
    @classmethod
    def validate_factor(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("O fator deve ser maior que zero")
        return v

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v < 0:
            raise ValueError("O preço não pode ser negativo")
        return round(v, 2)

    @field_validator("price_2", "price_3")
    @classmethod
    def validate_other_prices(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("O preço não pode ser negativo")
        return None if v is None else round(v, 2)

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


class ProductSaleUnitResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    unit_of_measure_id: uuid.UUID
    unit_of_measure_code: str | None = None
    factor: float
    price: float
    price_2: float | None = None
    price_3: float | None = None
    barcode: str | None
    is_active: bool

    class Config:
        from_attributes = True
