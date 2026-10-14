"""Inventário - requests of the inventory screen (the responses are the service's dicts)."""
import uuid

from pydantic import BaseModel


class InventoryCreateRequest(BaseModel):
    warehouse_id: uuid.UUID
    fiscal_period_id: uuid.UUID | None = None  # the soft-closed period for the inventory of the month just ended
    description: str | None = None


class InventoryCount(BaseModel):
    product_id: uuid.UUID
    counted_quantity: float | None = None  # base unit; None = not counted
    count_detail: str | None = None


class InventoryCountsRequest(BaseModel):
    counts: list[InventoryCount]
