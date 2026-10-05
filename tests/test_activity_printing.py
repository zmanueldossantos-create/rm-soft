"""Printing after a sale is an activity setting: stored, kept when the activity is only renamed, and refused when
switched on without any format."""
import pytest

from app.services.activity_service import ActivityPrintError, update_activity


@pytest.mark.asyncio
async def test_the_printing_settings_are_stored(db, company_with_essentials):
    ctx = company_with_essentials
    activity = await update_activity(db, ctx["company"].id, ctx["activity"].id, ctx["activity"].name,
                                     print_after_sale=True, print_ticket=True, print_a4=True)
    assert activity.print_after_sale and activity.print_ticket and activity.print_a4


@pytest.mark.asyncio
async def test_renaming_keeps_the_printing(db, company_with_essentials):
    ctx = company_with_essentials
    await update_activity(db, ctx["company"].id, ctx["activity"].id, ctx["activity"].name,
                          print_after_sale=True, print_ticket=False, print_a4=True)
    renamed = await update_activity(db, ctx["company"].id, ctx["activity"].id, "Novo nome")
    assert renamed.name == "Novo nome" and renamed.print_after_sale and not renamed.print_ticket and renamed.print_a4


@pytest.mark.asyncio
async def test_printing_without_any_format_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    with pytest.raises(ActivityPrintError):
        await update_activity(db, ctx["company"].id, ctx["activity"].id, ctx["activity"].name,
                              print_after_sale=True, print_ticket=False, print_a4=False)
