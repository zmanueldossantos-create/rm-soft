"""CompanyDocumentTypePreference: per-company override of requires_payment_term (default off, like available_at_pos)."""
import pytest
from sqlalchemy import text

from app.services.company_document_type_service import list_document_type_preferences, set_document_type_preference


@pytest.mark.asyncio
async def test_absence_of_a_row_means_follow_platform_default_false(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    prefs = await list_document_type_preferences(db, company_id)
    ft = next(p for p in prefs if p["code"] == "FT")
    assert ft["requires_payment_term"] is False  # no row yet: company-level default is off


@pytest.mark.asyncio
async def test_set_preference_creates_then_updates_a_row(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    ft_id = (await db.execute(text("SELECT id FROM document_types WHERE code = 'FT'"))).scalar_one()

    await set_document_type_preference(db, company_id, ft_id, True)
    prefs = await list_document_type_preferences(db, company_id)
    assert next(p for p in prefs if p["code"] == "FT")["requires_payment_term"] is True

    await set_document_type_preference(db, company_id, ft_id, False)
    prefs = await list_document_type_preferences(db, company_id)
    assert next(p for p in prefs if p["code"] == "FT")["requires_payment_term"] is False