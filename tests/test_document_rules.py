"""The rules of a document are read from the catalog row, in one place."""
import pytest

from app.models.document_type import DocumentType
from app.services import document_rules


def test_rules_from_row_reads_every_column():
    row = DocumentType(
        code="ZQ7", name="x", saft_section="PAYMENTS", revenue_sign=-1, requires_origin=True, has_lines=False,
        paid_on_issue=True, sent_to_agt=True, deducts_stock=True, accepts_credit_note=True, accepts_debit_note=True,
        accepts_receipt=True, convertible=True, issuable_in_invoices=True, issuable_at_pos=True,
    )
    rules = document_rules.rules_from_row(row)
    assert (rules.code, rules.saft_section, rules.revenue_sign, rules.has_lines) == ("ZQ7", "PAYMENTS", -1, False)
    assert all([
        rules.requires_origin, rules.paid_on_issue, rules.sent_to_agt, rules.deducts_stock, rules.accepts_credit_note,
        rules.accepts_debit_note, rules.accepts_receipt, rules.convertible, rules.issuable_in_invoices, rules.issuable_at_pos,
    ])


@pytest.mark.asyncio
async def test_get_document_rules_reads_the_catalog_row(db, monkeypatch):
    monkeypatch.setitem(document_rules.DOC_CODE_BY_INVOICE_TYPE, "TIPO_TESTE", "ZQ8")
    db.add(DocumentType(code="ZQ8", name="Tipo de teste", saft_section="WORKING", accepts_receipt=True))
    await db.commit()

    rules = await document_rules.get_document_rules(db, "TIPO_TESTE")
    assert rules.code == "ZQ8" and rules.saft_section == "WORKING"
    assert rules.accepts_receipt is True and rules.sent_to_agt is False  # everything else off by default
    with pytest.raises(document_rules.DocumentRulesNotFoundError):
        await document_rules.get_document_rules(db, "ZQ0")