"""
Pydantic schemas for PointOfSale (POS) CRUD - nested under an Activity.
"""
import uuid

from pydantic import BaseModel


class PosCreateRequest(BaseModel):
    activity_id: uuid.UUID
    name: str
    billetage_enabled: bool = False
    allow_price_levels: bool = False  # the cashier may choose «Preço 2 / Preço 3»
    allow_free_price: bool = False  # the cashier may type a free price

    print_after_sale: bool = False
    print_ticket: bool = True
    print_a4: bool = False
    accept_closing_difference: bool = True
    print_closing_report: bool = False


class PosUpdateRequest(BaseModel):
    name: str
    billetage_enabled: bool = False
    allow_price_levels: bool = False  # the cashier may choose «Preço 2 / Preço 3»
    allow_free_price: bool = False  # the cashier may type a free price

    print_after_sale: bool = False
    print_ticket: bool = True
    print_a4: bool = False
    accept_closing_difference: bool = True
    print_closing_report: bool = False


class PointOfSaleResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    activity_id: uuid.UUID
    name: str
    is_active: bool
    billetage_enabled: bool
    allow_price_levels: bool = False
    allow_free_price: bool = False

    print_after_sale: bool
    print_ticket: bool
    print_a4: bool
    accept_closing_difference: bool = True
    print_closing_report: bool = False
    is_default: bool = False

    class Config:
        from_attributes = True
