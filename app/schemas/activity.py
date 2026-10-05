"""
Pydantic schemas for Activity (business line / point of sale within a
Company - e.g. Padaria, Bar, Hotel) - GESTOR configures these, but only
for Modules the company has been granted by SUPER_ADMIN.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator



class ActivityCreateRequest(BaseModel):
    module_id: uuid.UUID
    name: str
    print_after_sale: bool = False
    print_ticket: bool = True
    print_a4: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome da atividade nao pode estar vazio")
        return cleaned


class ActivityUpdateRequest(BaseModel):
    name: str
    # Each print setting is applied only when sent: renaming an activity never touches its printing.
    print_after_sale: bool | None = None
    print_ticket: bool | None = None
    print_a4: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome da atividade nao pode estar vazio")
        return cleaned


class ActivityResponse(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    name: str
    is_active: bool
    print_after_sale: bool
    print_ticket: bool
    print_a4: bool
    created_at: datetime

    class Config:
        from_attributes = True
