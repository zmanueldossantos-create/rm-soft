"""Point 34a - an account opened by mistake is cancelled while empty: no fiscal document, the table is freed."""
import pytest

from app.models.open_account import OpenAccountStatus
from app.models.product import Product, ProductType
from app.services.open_account_service import (
    AccountAlreadyClosedError, InvalidLineError, add_line, cancel_empty_account, open_account,
)


async def _account(db, ctx, label):
    return await open_account(db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, label)


@pytest.mark.asyncio
async def test_an_empty_account_is_cancelled_without_any_document(db, company_with_essentials):
    ctx = company_with_essentials
    account = await cancel_empty_account(db, ctx["company"].id, (await _account(db, ctx, "Mesa 1")).id)
    assert account.status == OpenAccountStatus.FECHADA
    assert account.invoice_id is None
    with pytest.raises(AccountAlreadyClosedError):
        await cancel_empty_account(db, ctx["company"].id, account.id)


@pytest.mark.asyncio
async def test_an_account_with_articles_is_never_cancelled(db, company_with_essentials):
    ctx = company_with_essentials
    dish = Product(company_id=ctx["company"].id, code="OAC-1", name="Muamba", vat_id=ctx["vat_nor"].id, price=4500,
                   min_stock_threshold=0, product_type=ProductType.BEM, managed_by_stock=False)
    db.add(dish)
    await db.commit()
    account = await _account(db, ctx, "Mesa 2")
    await add_line(db, ctx["company"].id, account.id, ctx["gestor"].id, 1, product_id=dish.id)
    with pytest.raises(InvalidLineError, match="sem artigos"):
        await cancel_empty_account(db, ctx["company"].id, account.id)
