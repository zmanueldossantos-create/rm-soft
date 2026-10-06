import uuid
from datetime import datetime

from pydantic import BaseModel


class KitchenLine(BaseModel):
    id: uuid.UUID
    name: str
    quantity: float
    unit_code: str | None = None
    status: str
    modified: bool = False
    cancel_reason: str | None = None


class KitchenCard(BaseModel):
    id: uuid.UUID
    number: int
    account_label: str
    activity_name: str
    sent_by_name: str
    sent_at: datetime
    lines: list[KitchenLine]


class KitchenBoardResponse(BaseModel):
    orders: list[KitchenCard]
    recent: list[KitchenCard]


class KitchenLineActionRequest(BaseModel):
    quantity: float | None = None  # the 'quantity' action only: the new, lower quantity


class KitchenHistoryLine(KitchenLine):
    started_at: datetime | None = None
    started_by_name: str | None = None
    ready_at: datetime | None = None
    ready_by_name: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by_name: str | None = None
    prep_minutes: float | None = None  # from 'Comecar' to 'Pronto'
    wait_minutes: float | None = None  # from the sending to 'Pronto' (what the customer waited)


class KitchenHistoryOrder(KitchenCard):
    lines: list[KitchenHistoryLine]
    dishes: int
    cancelled: int
    total_minutes: float | None = None  # from the sending to the last dish ready


class KitchenHistorySummary(BaseModel):
    orders: int
    served: int
    cancelled: int
    sold_out: int
    average_wait_minutes: float | None = None


class KitchenHistoryResponse(BaseModel):
    summary: KitchenHistorySummary
    orders: list[KitchenHistoryOrder]
