"""
PaymentMethodCatalog - the official AGT PaymentMechanism catalog (SAF-T AO
XSD, "Meio de pagamento" - CC/Cartao credito, CD/Cartao debito, CH/Cheque
bancario, CI/Credito documentario internacional, CO/Cheque ou cartao
oferta, CS/Compensacao de saldos, DE/Dinheiro electronico, MB/Referencias
Multicaixa, NU/Numerario, OU/Outros, PR/Permuta de bens, TB/Transferencia
bancaria), SUPER_ADMIN managed - these 12 codes are fixed by AGT, not
company-editable, same principle as VAT rates.

RECONCILED (this is the "future step" referenced in the original docstring
here): Payment.payment_method_id now points directly at this catalog -
there is no separate fixed enum anymore. is_cash marks the one entry (NU)
that represents physical cash in the drawer, used by
cash_session_service.close_session to compute the expected float instead
of a hardcoded enum comparison.

Which of the 12 codes a given company's cashiers see on the Caixa screen
is NOT stored here (this table is shared platform-wide across every
company) - see CompanyPaymentMethodPreference for that per-company choice,
managed by each company's own GESTOR.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class PaymentMethodCatalog(Base):
    __tablename__ = "payment_method_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(4), nullable=False, unique=True)  # e.g. "NU", "TB" - fixed AGT PaymentMechanism codes
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    allows_payment: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allows_receipt: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<PaymentMethodCatalog {self.code} - {self.name}>"
