"""
The AGT's test taxpayers (homologação): NIFs the AGT gives to the software producers with their private keys, so that
documents can be sent in the test environment before a real company has adhered. Platform-wide (SUPER_ADMIN); a
company picks one in Definições da Empresa → Faturação Eletrónica, and while the environment is Homologação its calls
go out under that NIF, signed with that key. Never used in Produção.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgtTestTaxpayer(Base):
    __tablename__ = "agt_test_taxpayers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nif: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    private_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # app.core.secret_box
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
