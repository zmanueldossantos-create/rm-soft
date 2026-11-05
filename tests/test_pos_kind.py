"""
Caixas: a point of sale is one cash drawer - a CAIXA sells, the COFRE (the safe) never does; the activity's own till
is always a CAIXA, and a till changes kind only with no session open.
"""
import pytest

from app.models.stock import Stock
from app.services.cash_session_service import open_session
from app.services.point_of_sale_service import (
    DefaultPosNotModifiableError, create_point_of_sale, update_point_of_sale,
)
from app.services.pos_service import CofreSaleError, checkout, create_pro_forma_from_pos
from tests.test_pos_service import _make_product


@pytest.mark.asyncio
async def test_the_safe_never_sells(db, company_with_essentials):
    ctx = company_with_essentials
    company = ctx["company"]
    product = await _make_product(db, company, ctx["vat_ise"], exemption_reason_id=ctx["exemption_m11"].id, price=1000.0)
    db.add(Stock(company_id=company.id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id, quantity=5))
    await db.commit()
    cofre = await create_point_of_sale(db, company.id, ctx["pos"].activity_id, "Cofre", kind="COFRE")
    assert cofre.kind.value == "COFRE"
    await open_session(db, company.id, cofre.id, ctx["gestor"], opening_amount=0)
    lines = [{"product_id": product.id, "quantity": 1}]
    with pytest.raises(CofreSaleError, match="cofre"):
        await checkout(db, company.id, cofre.id, ctx["gestor"], None, lines,
                       [{"payment_method_id": ctx["pm_numerario"].id, "amount": 1000.0}])
    with pytest.raises(CofreSaleError):
        await create_pro_forma_from_pos(db, company.id, cofre.id, ctx["gestor"], None, lines)


@pytest.mark.asyncio
async def test_the_kind_changes_only_when_nothing_runs(db, company_with_essentials):
    ctx = company_with_essentials
    company = ctx["company"]
    till = await create_point_of_sale(db, company.id, ctx["pos"].activity_id, "Caixa 2")
    assert till.kind.value == "CAIXA"
    till = await update_point_of_sale(db, company.id, till.id, "Cofre", kind="COFRE")
    assert till.kind.value == "COFRE"
    till = await update_point_of_sale(db, company.id, till.id, "Cofre")  # no kind sent: unchanged
    assert till.kind.value == "COFRE"
    await open_session(db, company.id, till.id, ctx["gestor"], opening_amount=0)
    with pytest.raises(DefaultPosNotModifiableError, match="Feche a sessão"):
        await update_point_of_sale(db, company.id, till.id, "Cofre", kind="CAIXA")
    default = ctx["pos"]
    if default.is_default:
        with pytest.raises(DefaultPosNotModifiableError, match="por defeito"):
            await update_point_of_sale(db, company.id, default.id, default.name, kind="COFRE")
