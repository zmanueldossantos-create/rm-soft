"""Document type rules from the admin screen: fiscal rules locked on an official type, usage rules always editable."""
import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.schemas.catalog import DocumentTypeRequest
from app.services.catalog_service import DocumentTypeRuleLockedError, create_document_type, update_document_type


@pytest.mark.asyncio
async def test_fiscal_rules_are_locked_on_an_official_type_and_usage_rules_are_not(db):
    item = await create_document_type(db, "ZQ5", "Tipo de teste", None, False, True, {"saft_section": "INVOICES", "sent_to_agt": True})
    item_id = item.id
    assert item.saft_section == "INVOICES" and item.sent_to_agt is True and item.rules_locked is False

    changed = await update_document_type(db, item_id, "ZQ5", "Tipo de teste", None, False, True, {"sent_to_agt": False})
    assert changed.sent_to_agt is False  # a type that is not locked: every rule editable

    await db.execute(text("UPDATE document_types SET rules_locked = true WHERE id = :id"), {"id": item_id})
    await db.commit()
    with pytest.raises(DocumentTypeRuleLockedError):
        await update_document_type(db, item_id, "ZQ5", "Tipo de teste", None, False, True, {"sent_to_agt": True})

    ok = await update_document_type(db, item_id, "ZQ5", "Tipo de teste", None, False, True, {"sent_to_agt": False, "accepts_receipt": True})
    assert ok.accepts_receipt is True and ok.sent_to_agt is False  # same fiscal value + a usage change
    same = await update_document_type(db, item_id, "ZQ5", "Tipo de teste", None, False, True, None)
    assert same.accepts_receipt is True  # no rules sent: unchanged


def test_request_only_carries_the_rules_that_were_sent():
    assert DocumentTypeRequest(code="X", name="Y", accepts_receipt=True).rules_dict() == {"accepts_receipt": True}
    assert DocumentTypeRequest(code="X", name="Y").rules_dict() == {}
    with pytest.raises(ValidationError):
        DocumentTypeRequest(code="X", name="Y", saft_section="AUTRE")