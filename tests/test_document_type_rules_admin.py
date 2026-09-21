"""Document type rules from the admin screen: every rule is editable, whatever the type."""
import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.schemas.catalog import DocumentTypeRequest
from app.services.catalog_service import create_document_type, update_document_type


@pytest.mark.asyncio
async def test_every_rule_is_editable_even_on_a_type_flagged_official(db):
    item = await create_document_type(db, "ZQ5", "Tipo de teste", None, False, True, {"saft_section": "INVOICES", "sent_to_agt": True})
    item_id = item.id
    assert item.saft_section == "INVOICES" and item.sent_to_agt is True

    await db.execute(text("UPDATE document_types SET rules_locked = true WHERE id = :id"), {"id": item_id})
    await db.commit()
    changed = await update_document_type(
        db, item_id, "ZQ5", "Tipo de teste", None, False, True,
        {"sent_to_agt": False, "saft_section": "WORKING", "accepts_receipt": True},
    )
    assert (changed.sent_to_agt, changed.saft_section, changed.accepts_receipt) == (False, "WORKING", True)
    same = await update_document_type(db, item_id, "ZQ5", "Tipo de teste", None, False, True, None)
    assert same.saft_section == "WORKING"  # no rules sent: unchanged


def test_request_only_carries_the_rules_that_were_sent():
    assert DocumentTypeRequest(code="X", name="Y", accepts_receipt=True).rules_dict() == {"accepts_receipt": True}
    assert DocumentTypeRequest(code="X", name="Y").rules_dict() == {}
    with pytest.raises(ValidationError):
        DocumentTypeRequest(code="X", name="Y", saft_section="AUTRE")
