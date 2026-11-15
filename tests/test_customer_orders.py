"""Encomendas (capability ORDERS), step 1: a customer's order with its delivery and production notes, numbered
ENC<year>/n, changed while not ready, moved through production one step at a time, cancelled with a reason - and only
in an activity whose sector has the Encomendas."""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models.activity import Activity
from app.models.module_capability import ModuleCapability
from app.models.product import Product, ProductType
from app.services.customer_order_service import (
    CustomerOrderError, cancel_order, create_order, list_orders, order_options, set_production_status, update_order,
)
from app.services.customer_service import create_customer

LUANDA = ZoneInfo("Africa/Luanda")


async def _setup(db, ctx, with_orders=True):
    company_id = ctx["company"].id
    activity = await db.get(Activity, ctx["activity"].id)
    if with_orders:
        db.add(ModuleCapability(module_id=activity.module_id, capability="ORDERS", is_enabled=True))
    cake = Product(company_id=company_id, code="BOL" + uuid.uuid4().hex[:4], name="Bolo de chocolate", vat_id=ctx["vat_nor"].id,
                   price=10000, min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                   managed_by_stock=False)
    db.add(cake)
    await db.commit()
    customer = await create_customer(db, company_id, "Ana Silva", "002614524LA055", phone_number="+244923000222")
    return activity, cake, customer


def _order(customer, cake, **extra):
    return {"customer_id": customer.id, "delivery_at": datetime.now(LUANDA) + timedelta(days=2), "delivery_mode": "LOJA",
            "lines": [{"product_id": cake.id, "quantity": 2, "production_note": "Parabéns Ana 30 anos"}], **extra}


@pytest.mark.asyncio
async def test_an_order_from_its_creation_to_ready(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    activity, cake, customer = await _setup(db, ctx)

    options = await order_options(db, company_id)
    assert [a["name"] for a in options["activities"]] == [activity.name]
    assert any(a["name"] == "Bolo de chocolate" and a["price"] == 10000.0 for a in options["articles"])

    order = await create_order(db, company_id, user_id, _order(customer, cake))
    year = datetime.now(LUANDA).year
    assert order["reference"] == f"ENC{year}/1" and order["status"] == "ENCOMENDADA"
    assert order["activity_id"] == activity.id  # the only activity with Encomendas
    assert (order["subtotal"], order["vat"], order["total"]) == (20000.0, 2800.0, 22800.0)  # the article's price and rate
    assert order["lines"][0]["production_note"] == "Parabéns Ana 30 anos"
    second = await create_order(db, company_id, user_id, _order(customer, cake, delivery_mode="ENTREGA",
                                                                 delivery_address="Rua 1, Kilamba"))
    assert second["reference"] == f"ENC{year}/2"

    changed = await update_order(db, company_id, order["id"], _order(
        customer, cake, lines=[{"product_id": cake.id, "quantity": 1, "unit_price": 12000}]))
    assert changed["total"] == 13680.0 and len(changed["lines"]) == 1

    await set_production_status(db, company_id, order["id"], "EM_PRODUCAO")
    ready = await set_production_status(db, company_id, order["id"], "PRONTA")
    assert ready["status"] == "PRONTA" and ready["editable"] is False
    with pytest.raises(CustomerOrderError, match="já não se altera"):
        await update_order(db, company_id, order["id"], _order(customer, cake))
    with pytest.raises(CustomerOrderError, match="não pode passar"):
        await set_production_status(db, company_id, order["id"], "ENTREGUE")  # the delivery is done at the till
    back = await set_production_status(db, company_id, order["id"], "EM_PRODUCAO")  # a cake to redo
    assert back["status"] == "EM_PRODUCAO"

    with pytest.raises(CustomerOrderError, match="motivo"):
        await cancel_order(db, company_id, second["id"], " ")
    cancelled = await cancel_order(db, company_id, second["id"], "Cliente desistiu")
    assert (cancelled["status"], cancelled["cancel_reason"]) == ("CANCELADA", "Cliente desistiu")
    with pytest.raises(CustomerOrderError, match="não se cancela"):
        await cancel_order(db, company_id, second["id"], "Outra vez")

    opened = await list_orders(db, company_id, status="ABERTAS")
    assert [o["reference"] for o in opened] == [order["reference"]]
    found = await list_orders(db, company_id, search="ana")
    assert len(found) == 2


@pytest.mark.asyncio
async def test_what_an_order_refuses(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    _, cake, customer = await _setup(db, ctx)
    with pytest.raises(CustomerOrderError, match="já passou"):
        await create_order(db, company_id, user_id, _order(customer, cake, delivery_at=datetime.now(LUANDA) - timedelta(days=1)))
    with pytest.raises(CustomerOrderError, match="morada"):
        await create_order(db, company_id, user_id, _order(customer, cake, delivery_mode="ENTREGA"))
    with pytest.raises(CustomerOrderError, match="pelo menos um artigo"):
        await create_order(db, company_id, user_id, _order(customer, cake, lines=[]))
    with pytest.raises(CustomerOrderError, match="quantidade"):
        await create_order(db, company_id, user_id, _order(customer, cake, lines=[{"product_id": cake.id, "quantity": 0}]))
    final = await create_customer(db, company_id, "Consumidor final", "999999999")
    final.is_final_consumer = True
    await db.commit()
    with pytest.raises(CustomerOrderError, match="cliente identificado"):
        await create_order(db, company_id, user_id, _order(final, cake))


@pytest.mark.asyncio
async def test_no_order_where_the_sector_has_no_encomendas(db, company_with_essentials):
    ctx = company_with_essentials
    _, cake, customer = await _setup(db, ctx, with_orders=False)
    assert (await order_options(db, ctx["company"].id))["activities"] == []
    with pytest.raises(CustomerOrderError, match="Nenhuma atividade"):
        await create_order(db, ctx["company"].id, ctx["gestor"].id, _order(customer, cake))
