"""
Platform-wide settings model - a single row, not scoped to any company.
See discussion on SoftwareValidationNumber: this number is issued by the
AGT to the SOFTWARE PRODUCT itself (RM SOFT), not to each client company -
so it applies uniformly to every company's SAF-T export, set once here by
SUPER_ADMIN, regardless of Mode A (local) or Mode B (SaaS) deployment.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Null until AGT homologates RM SOFT - the SAF-T generator falls back
    # to a clearly-marked simulated placeholder when this is unset.
    software_validation_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # SAF-T Header.ProductCompanyTaxID - the SOFTWARE VENDOR's own NIF
    # (RM SOFT / the developer business), NOT the client company's NIF.
    vendor_tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # SAF-T Header.ProductID, e.g. "RMSOFT/RMSOFT"
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # SAF-T Header.ProductVersion
    product_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<PlatformSettings validation_number={self.software_validation_number}>"
