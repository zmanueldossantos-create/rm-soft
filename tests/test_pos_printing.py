"""Printing after a sale is set per till: even the activity's default till keeps its setting, and switching it on
without any format is refused."""
import pytest

from app.services.point_of_sale_service import PosPrintError, update_point_of_sale


@pytest.mark.asyncio
async def test_the_default_till_keeps_its_printing(db, company_with_essentials):
    ctx = company_with_essentials
    pos = ctx["pos"]
    updated = await update_point_of_sale(db, ctx["company"].id, pos.id, pos.name,
                                         print_after_sale=True, print_ticket=False, print_a4=True)
    assert updated.print_after_sale and not updated.print_ticket and updated.print_a4


@pytest.mark.asyncio
async def test_printing_without_any_format_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    with pytest.raises(PosPrintError):
        await update_point_of_sale(db, ctx["company"].id, ctx["pos"].id, ctx["pos"].name,
                                   print_after_sale=True, print_ticket=False, print_a4=False)
