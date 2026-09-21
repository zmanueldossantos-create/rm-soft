"""A document type carries its behaviour as columns: a new type starts with everything off (lines allowed), and the API exposes them."""
import pytest

from app.models.document_type import DocumentType
from app.schemas.catalog import DocumentTypeResponse

FLAGS = [
    "rules_locked", "requires_origin", "paid_on_issue", "sent_to_agt", "deducts_stock", "accepts_credit_note",
    "accepts_debit_note", "accepts_receipt", "convertible", "issuable_in_invoices", "issuable_at_pos",
]


@pytest.mark.asyncio
async def test_a_new_document_type_starts_with_everything_off(db):
    item = DocumentType(code="ZQ9", name="Tipo de teste")
    db.add(item)
    await db.commit()
    await db.refresh(item)
    assert item.saft_section == "NONE" and item.revenue_sign == 0 and item.has_lines is True
    assert all(getattr(item, flag) is False for flag in FLAGS)


def test_the_response_schema_exposes_the_rules():
    for name in FLAGS + ["saft_section", "revenue_sign", "has_lines"]:
        assert name in DocumentTypeResponse.model_fields