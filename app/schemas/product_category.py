"""Pydantic schemas for ProductCategory (Video 3, company-scoped)."""
import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator


class ProductCategoryRequest(BaseModel):
    name: str
    not_available_purchases: bool = False
    not_available_pos: bool = False
    not_available_sales: bool = False
    activity_ids: list[uuid.UUID] = []  # the activities whose tills offer its products - empty: every activity

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome da categoria não pode estar vazio")
        return cleaned


class ProductCategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    not_available_purchases: bool
    not_available_pos: bool
    not_available_sales: bool
    activity_ids: list[uuid.UUID] = []
    is_active: bool
    created_at: datetime

    @field_validator("activity_ids", mode="before")
    @classmethod
    def no_activity_means_all(cls, v):
        return v or []

    class Config:
        from_attributes = True
