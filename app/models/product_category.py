"""
ProductCategory - company-scoped catalog (Video 3: "Categoria de Produto")
- unlike the platform-wide catalogs in Configuracoes, this is managed by
each company's own GESTOR, since a bakery's categories (Paes, Bolos) have
nothing to do with a pharmacy's.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    not_available_purchases: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    not_available_pos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    not_available_sales: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ProductCategory {self.name}>"
