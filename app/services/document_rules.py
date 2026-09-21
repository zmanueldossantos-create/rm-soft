"""
Behaviour of a document, read from the document type catalog (document_types) - one place, instead of comparing
document types by name all over the code. The columns are set by the super admin (the fiscal rules of the official
types are locked) - see DocumentType.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_type import DocumentType

# The stored invoice type (Invoice.invoice_type) -> the code of its document type in the catalog.
# The only place that maps the two.
DOC_CODE_BY_INVOICE_TYPE = {
    "FACTURA": "FT", "FACTURA_RECIBO": "FR", "NOTA_CREDITO": "NC", "NOTA_DEBITO": "ND", "RECIBO": "RC", "PRO_FORMA": "FP",
}


class DocumentRulesNotFoundError(Exception):
    """The document type is not in the catalog: nothing is assumed about it."""


@dataclass(frozen=True)
class DocumentRules:
    code: str
    saft_section: str  # INVOICES | PAYMENTS | WORKING | NONE
    revenue_sign: int  # +1 sale, -1 credit note, 0 not counted
    requires_origin: bool
    has_lines: bool
    paid_on_issue: bool
    sent_to_agt: bool
    deducts_stock: bool
    accepts_credit_note: bool
    accepts_debit_note: bool
    accepts_receipt: bool
    convertible: bool
    issuable_in_invoices: bool
    issuable_at_pos: bool


def rules_from_row(row: DocumentType) -> DocumentRules:
    return DocumentRules(
        code=row.code, saft_section=row.saft_section, revenue_sign=row.revenue_sign, requires_origin=row.requires_origin,
        has_lines=row.has_lines, paid_on_issue=row.paid_on_issue, sent_to_agt=row.sent_to_agt,
        deducts_stock=row.deducts_stock, accepts_credit_note=row.accepts_credit_note,
        accepts_debit_note=row.accepts_debit_note, accepts_receipt=row.accepts_receipt, convertible=row.convertible,
        issuable_in_invoices=row.issuable_in_invoices, issuable_at_pos=row.issuable_at_pos,
    )


async def get_document_rules(db: AsyncSession, invoice_type) -> DocumentRules:
    """Rules of a document, from its stored invoice type (or directly its catalog code, e.g. "FT")."""
    value = getattr(invoice_type, "value", invoice_type)
    code = DOC_CODE_BY_INVOICE_TYPE.get(value, value)
    row = (await db.execute(select(DocumentType).where(DocumentType.code == code))).scalar_one_or_none()
    if row is None:
        raise DocumentRulesNotFoundError(f"Tipo de documento '{code}' nao existe no catalogo")
    return rules_from_row(row)