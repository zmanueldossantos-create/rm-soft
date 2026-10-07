"""
Pydantic schemas for PointOfSale (POS) CRUD - nested under an Activity.
"""
import uuid

from pydantic import BaseModel


class PosCreateRequest(BaseModel):
    activity_id: uuid.UUID
    name: str
    billetage_enabled: bool = False

    print_after_sale: bool = False
    print_ticket: bool = True
    print_a4: bool = False
    accept_closing_difference: bool = True
    print_closing_report: bool = False


class PosUpdateRequest(BaseModel):
    name: str
    billetage_enabled: bool = False

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

    print_after_sale: bool
    print_ticket: bool
    print_a4: bool
    accept_closing_difference: bool = True
    print_closing_report: bool = False
    is_default: bool = False

    class Config:
        from_attributes = True
