"""Point 34a - the account cards show each account's number of lines and total, computed by the listing."""
import pytest

from app.models.product import Product, ProductType
from app.schemas.open_account import OpenAccountResponse
from app.services.open_account_service import add_line, list_open_accounts, open_account


@pytest.mark.asyncio
async def test_the_list_gives_each_account_its_lines_and_total(db, company_with_essentials):
    ctx = company_with_essentials
    cid, uid = ctx["company"].id, ctx["gestor"].id
    dish = Product(company_id=cid, code="OAL-1", name="Muamba", vat_id=ctx["vat_ise"].id, price=4500,
                   min_stock_threshold=0, product_type=ProductType.BEM, managed_by_stock=False)
    beer = Product(company_id=cid, code="OAL-2", name="Cuca", vat_id=ctx["vat_ise"].id, price=600,
                   min_stock_threshold=0, product_type=ProductType.BEM, managed_by_stock=False)
    db.add_all([dish, beer])
    await db.commit()
    table = await open_account(db, cid, ctx["activity"].id, ctx["pos"].id, uid, "Mesa 1")
    empty = await open_account(db, cid, ctx["activity"].id, ctx["pos"].id, uid, "Mesa 2")
    await add_line(db, cid, table.id, uid, 1, product_id=dish.id)
    await add_line(db, cid, table.id, uid, 2, product_id=beer.id)

    accounts = {a.id: OpenAccountResponse.model_validate(a) for a in await list_open_accounts(db, cid, ctx["activity"].id)}
    assert (accounts[table.id].line_count, accounts[table.id].total) == (2, 5700)
    assert (accounts[empty.id].line_count, accounts[empty.id].total) == (0, 0)
