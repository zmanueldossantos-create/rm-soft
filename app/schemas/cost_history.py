"""Histórico do custo - the entries that moved a product's weighted average cost (see cost_history_service)."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel


class CostHistoryEntry(BaseModel):
    id: uuid.UUID
    kind: str  # "RECEPCAO" | "PRODUCAO"
    date: date
    created_at: datetime
    reference: str | None
    supplier: str | None
    warehouse: str | None
    quantity: float
    unit_cost: float | None
    cost_before: float | None
    cost_after: float | None
    change_pct: float | None


class CostHistoryResponse(BaseModel):
    current_cost: float | None
    last_purchase_price: float | None
    min_unit_cost: float | None
    max_unit_cost: float | None
    entries: list[CostHistoryEntry]
