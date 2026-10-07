"""Point 34a - an account costs what its invoice will charge: price before VAT, VAT per line, same rounding."""
import pytest

from app.models.product import Product, ProductType
from app.schemas.open_account import OpenAccountLineResponse, OpenAccountResponse
from app.services.open_account_service import add_line, list_account_lines, list_open_accounts, open_account


@pytest.mark.asyncio
async def test_lines_and_account_carry_the_vat_the_invoice_will_charge(db, company_with_essentials):
    ctx = company_with_essentials
    cid, uid = ctx["company"].id, ctx["gestor"].id
    dish = Product(company_id=cid, code="OAV-1", name="Muamba", vat_id=ctx["vat_nor"].id, price=4500,
                   min_stock_threshold=0, product_type=ProductType.BEM, managed_by_stock=False)
    beer = Product(company_id=cid, code="OAV-2", name="Cuca", vat_id=ctx["vat_nor"].id, price=600,
                   min_stock_threshold=0, product_type=ProductType.BEM, managed_by_stock=False)
    db.add_all([dish, beer])
    await db.commit()
    table = await open_account(db, cid, ctx["activity"].id, ctx["pos"].id, uid, "Mesa 1")
    await add_line(db, cid, table.id, uid, 1, product_id=dish.id)
    await add_line(db, cid, table.id, uid, 2, product_id=beer.id)

    lines = {l.name_snapshot: OpenAccountLineResponse.model_validate(l) for l in await list_account_lines(db, table.id)}
    assert (lines["Muamba"].line_subtotal, lines["Muamba"].line_vat, lines["Muamba"].line_total) == (4500, 630, 5130)
    assert (lines["Cuca"].line_subtotal, lines["Cuca"].line_vat, lines["Cuca"].line_total) == (1200, 168, 1368)

    account = next(OpenAccountResponse.model_validate(a) for a in await list_open_accounts(db, cid, ctx["activity"].id) if a.id == table.id)
    assert (account.line_count, account.subtotal, account.vat_total, account.total) == (2, 5700, 798, 6498)
