"""«Pedir demonstração» - the public site's form, and the SUPER_ADMIN's follow-up («Pedidos»)."""
import uuid

from pydantic import BaseModel, Field


class DemoRequestCreate(BaseModel):
    name: str = Field(default="", max_length=200)
    company_name: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    email: str | None = Field(default=None, max_length=200)
    nif: str | None = Field(default=None, max_length=40)
    sectors: list[str] = Field(default=[], max_length=20)
    plan_id: uuid.UUID | None = None
    deployment: str | None = None
    message: str | None = Field(default=None, max_length=2000)
    language: str = "pt"
    fax: str | None = Field(default=None, max_length=200)  # the hidden field: a person leaves it empty
    elapsed_ms: float = 0  # how long the form was open before being sent


class DemoRequestUpdate(BaseModel):
    status: str
    notes: str | None = Field(default=None, max_length=2000)
