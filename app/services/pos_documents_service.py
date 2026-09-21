"""Documents shown by the Caixa ("Consultar documentos")."""
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cash_session import CashSession
from app.models.document_type import DocumentType
from app.models.invoice import DocumentLifecycleStatus, Invoice, InvoiceType
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE


async def list_pos_documents(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID, limit: int = 30) -> list[Invoice]:
    """The documents of this cash point's sessions, plus the invoices - from anywhere - that still await a payment (so
    the cashier can issue the receipt). Newest first. What counts as a document to show (SAF-T section) and which types
    take a receipt (accepts_receipt) come from the document type catalog. A pro-forma is not listed (it has its own list)."""
    rows = (await db.execute(select(DocumentType.code, DocumentType.saft_section, DocumentType.accepts_receipt))).all()
    stored_by_code = {code: stored for stored, code in DOC_CODE_BY_INVOICE_TYPE.items()}
    shown = [InvoiceType(stored_by_code[c]) for c, section, _ in rows if c in stored_by_code and section in ("INVOICES", "PAYMENTS")]
    receivable = [InvoiceType(stored_by_code[c]) for c, _, accepts in rows if c in stored_by_code and accepts]

    session_ids = select(CashSession.id).where(CashSession.company_id == company_id, CashSession.pos_id == pos_id)
    balance = Invoice.total - func.coalesce(Invoice.retention_total, 0) - func.coalesce(Invoice.amount_received, 0)
    awaiting_payment = and_(
        Invoice.invoice_type.in_(receivable),
        Invoice.document_status != DocumentLifecycleStatus.ANULADO,
        balance > 0.005,
    )
    query = (
        select(Invoice)
        .where(Invoice.company_id == company_id, Invoice.invoice_type.in_(shown),
               or_(Invoice.cash_session_id.in_(session_ids), awaiting_payment))
        .order_by(Invoice.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(query)).scalars().all())