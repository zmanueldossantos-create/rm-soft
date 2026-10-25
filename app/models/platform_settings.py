"""
Platform-wide settings model - a single row, not scoped to any company.
See discussion on SoftwareValidationNumber: this number is issued by the
AGT to the SOFTWARE PRODUCT itself (RM SOFT), not to each client company -
so it applies uniformly to every company's SAF-T export, set once here by
SUPER_ADMIN, regardless of Mode A (local) or Mode B (SaaS) deployment.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
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

    # The AI assistant: one provider and one key for every company (the platform pays), a message limit per company
    ai_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)  # OPENAI | ANTHROPIC | OPENROUTER
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)  # app.core.secret_box
    ai_monthly_limit: Mapped[int] = mapped_column(Integer, default=300, server_default="300", nullable=False)
    # The assistant on Telegram: one RM SOFT bot (in a local installation, the installation's own bot)
    telegram_bot_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_bot_username: Mapped[str | None] = mapped_column(String(100), nullable=True)  # read from Telegram (getMe)
    telegram_webhook_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SaaS: checks Telegram's calls
    # The assistant on WhatsApp: one RM SOFT number (WhatsApp Cloud API, Meta)
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(40), nullable=True)  # Meta's id of the number
    whatsapp_display_number: Mapped[str | None] = mapped_column(String(20), nullable=True)  # +244..., shown to the gestor
    whatsapp_access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_app_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)  # checks Meta's signature
    whatsapp_verify_token: Mapped[str | None] = mapped_column(String(64), nullable=True)  # given to Meta for the webhook

    # The public site (rmsystem.co.ao, PUBLIC_SITE): the contacts it shows - the WhatsApp button and the email
    site_whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)  # +244923000000
    site_email: Mapped[str | None] = mapped_column(String(120), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<PlatformSettings validation_number={self.software_validation_number}>"
