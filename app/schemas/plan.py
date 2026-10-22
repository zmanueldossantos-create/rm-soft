"""Planos and contracts (SUPER_ADMIN)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PlanRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=300)
    price_monthly: Decimal | None = None
    price_quarterly: Decimal | None = None
    price_semiannual: Decimal | None = None
    price_annual: Decimal | None = None
    price_lifetime: Decimal | None = None
    maintenance_percent: Decimal | None = None
    limits: dict[str, int | None] = {}
    options: list[str] = []
    is_popular: bool = False
    sort_order: int = 0
    is_active: bool = True


class PlanResponse(PlanRequest):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    companies: int = 0  # companies on this plan now


class ContractRequest(BaseModel):
    plan_id: uuid.UUID
    deployment_mode: str = "SAAS"
    billing: str = "ANUAL"
    start_date: date | None = None
    end_date: date | None = None  # empty: the end of the period paid (none for the lifetime licence)
    no_end: bool = False  # «Sem data de fim» (the companies of before the plans, an agreement...)
    maintenance_until: date | None = None
    addons: dict[str, int | None] = {}
    price: Decimal | None = None
    notes: str | None = Field(default=None, max_length=500)


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: str
    deployment_mode: str
    billing: str
    start_date: date
    end_date: date | None
    maintenance_until: date | None
    addons: dict
    price: Decimal | None
    notes: str | None
    is_current: bool
    created_at: datetime


class CompanyContractView(BaseModel):
    current: ContractResponse | None
    history: list[ContractResponse]
    limits: dict[str, int | None] | None  # the plan's + the add-ons; None: no contract (nothing limited)
    usage: dict[str, int]
