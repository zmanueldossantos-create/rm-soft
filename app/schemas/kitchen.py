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
