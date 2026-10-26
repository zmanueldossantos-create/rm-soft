"""
Notificações N2: the operations write their notification themselves, in their own transaction - a sale at the till,
a table opened and closed, a hotel check-in and check-out (at the reception or paid at the till), a till closed with
its difference, and a product going under its minimum (once, at the crossing). An action of the gestor himself is not
sent (unless switched on); the stock baixo always is.
"""
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.notification import NotificationOutbox, NotificationRecipient
from app.models.product import Product, ProductType
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service
from app.models.stock import Stock
from app.services.auth_service import create_user
from app.services.booking_service import create_booking
from app.services.cash_session_service import close_session, open_session
from app.services.hotel_service import LUANDA, check_in, check_out
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog
from app.services.open_account_service import add_line, close_account, open_account
from app.services.user_cash_point_access_service import assign_user_to_cash_point
from app.services.invoice_service import create_invoice

EVERYTHING = ["CHECK_IN", "CHECK_OUT", "MESA_ABERTA", "MESA_FECHADA", "VENDA", "CAIXA_FECHADA", "STOCK_BAIXO"]
BASE = (datetime.now(LUANDA) + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)


@pytest.fixture
async def team(db, company_with_essentials):
    """The owner receives everything by email; a cashier works at the till."""
    ctx = company_with_essentials
    company_id = ctx["company"].id
    db.add(NotificationRecipient(company_id=company_id, name="Dono", channel="EMAIL", address="dono@empresa.ao",
                                 events=EVERYTHING))
    cashier = await create_user(db, company_id, "João Caixa", "+244923000401", "Teste@2026", "CAIXA")
    await assign_user_to_cash_point(db, company_id, cashier.id, ctx["pos"].id)
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)
    await db.commit()
    return {**ctx, "cashier": cashier}


async def _messages(db, event=None):
    query = select(NotificationOutbox).order_by(NotificationOutbox.created_at)
    if event:
        query = query.where(NotificationOutbox.event == event)
    return (await db.execute(query)).scalars().all()


async def _product(db, ctx, code="P1", price=1000, stock=None, minimum=0):
    product = Product(company_id=ctx["company"].id, code=code, name="Donut" if code == "P1" else code,
                      vat_id=ctx["vat_nor"].id, price=price, min_stock_threshold=minimum, product_type=ProductType.BEM,
                      unit_of_measure_id=ctx["unit_un"].id)
    db.add(product)
    await db.flush()
    if stock is not None:
        db.add(Stock(company_id=ctx["company"].id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id,
                     quantity=stock))
    await db.commit()
    return product


async def test_a_sale_at_the_till(db, team):
    ctx = team
    product = await _product(db, ctx, stock=10)
    await open_session(db, ctx["company"].id, ctx["pos"].id, ctx["cashier"], 0)

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for user in (ctx["cashier"], ctx["gestor"]):
                h = {"Authorization": "Bearer " + create_access_token(
                    subject=str(user.id), company_id=str(ctx["company"].id), role=user.role.value)}
                sold = await client.post(f"/api/v1/pos/checkout/{ctx['pos'].id}", headers=h, json={
                    "invoice_type": "FACTURA_RECIBO", "lines": [{"product_id": str(product.id), "quantity": 1}],
                    "payments": [{"payment_method_id": str(ctx["pm_numerario"].id), "amount": 1140}]})
                assert sold.status_code == 201, sold.text
    finally:
        app.dependency_overrides.pop(get_db, None)
    sales = await _messages(db, "VENDA")
    assert len(sales) == 1  # the cashier's; the gestor's own sale is not sent
    first, *detail = sales[0].text.split("\n")
    assert first.startswith("Venda FR") and first.endswith(" - 1 140,00 Kz")
    assert detail == ["1 × Donut - 1 140,00 Kz", f"Pago: {ctx['pm_numerario'].name} 1 140,00 Kz",
                      f"Caixa: {ctx['pos'].name} · Vendedor: João Caixa"]
    assert sales[0].subject.startswith("Venda - ")


async def test_a_table_opened_and_closed(db, team):
    ctx = team
    product = await _product(db, ctx, stock=10)
    await open_session(db, ctx["company"].id, ctx["pos"].id, ctx["cashier"], 0)
    account = await open_account(db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["cashier"].id, "Mesa 5")
    await add_line(db, ctx["company"].id, account.id, ctx["cashier"].id, quantity=2, product_id=product.id)
    await close_account(db, ctx["company"].id, account.id, ctx["cashier"],
                        [{"payment_method_id": ctx["pm_numerario"].id, "amount": 2280.0}])
    events = [(m.event, m.text) for m in await _messages(db)]
    assert events[0] == ("MESA_ABERTA", "Mesa 5 aberta por João Caixa - Atividade Teste")
    assert events[1][0] == "MESA_FECHADA" and events[1][1].startswith("Mesa 5 fechada - 2 280,00 Kz (FR")
    assert events[1][1].split("\n")[1:] == ["2 × Donut - 2 280,00 Kz", f"Pago: {ctx['pm_numerario'].name} 2 280,00 Kz",
                                            "João Caixa"]
    assert len(events) == 2  # the closing of a table is not also a «Venda»


async def _room(db, ctx, requires_service=True):
    room_type = ResourceTypeCatalog(company_id=ctx["company"].id, name="Quarto", requires_service=requires_service)
    db.add(room_type)
    await db.flush()
    room = Resource(company_id=ctx["company"].id, activity_id=ctx["activity"].id, resource_type_id=room_type.id,
                    name="Quarto 101")
    night = Service(company_id=ctx["company"].id, code="HTL-DIA", name="Diária", price=25000, vat_id=ctx["vat_nor"].id,
                    unit_of_measure_id=ctx["unit_un"].id, resource_type_id=room_type.id)
    db.add_all([room, night])
    await db.commit()
    return room, night


async def test_a_hotel_stay(db, team):
    ctx = team
    room, night = await _room(db, ctx)
    await open_session(db, ctx["company"].id, ctx["pos"].id, ctx["cashier"], 0)
    booking = await create_booking(db, ctx["company"].id, room.id, ctx["cashier"].id, BASE, BASE + timedelta(days=2),
                                   service_id=night.id, guest_name="Ana Silva")
    booking, account = await check_in(db, ctx["company"].id, booking.id, ctx["cashier"])
    await close_account(db, ctx["company"].id, account.id, ctx["cashier"],
                        [{"payment_method_id": ctx["pm_numerario"].id, "amount": 57000.0}])  # 2 nights + 14 %
    events = [(m.event, m.text) for m in await _messages(db)]
    until = (BASE + timedelta(days=2)).strftime("%d/%m")
    assert events[0] == ("CHECK_IN", f"Quarto 101 ocupado - Ana Silva\n2 noites, até {until} · João Caixa")
    assert events[1][0] == "CHECK_OUT" and events[1][1].startswith("Quarto 101 libertado - Ana Silva\nTotal 57 000,00 Kz")
    assert len(events) == 2  # no «Mesa aberta» for the stay's account


async def test_a_check_out_with_nothing_to_pay(db, team):
    ctx = team
    room, _ = await _room(db, ctx, requires_service=False)  # no rate, so no line on the stay's account
    booking = await create_booking(db, ctx["company"].id, room.id, ctx["cashier"].id, BASE, BASE + timedelta(days=1),
                                   guest_name="Rui")
    booking, _ = await check_in(db, ctx["company"].id, booking.id, ctx["cashier"])
    await check_out(db, ctx["company"].id, booking.id, ctx["cashier"])
    assert [m.text for m in await _messages(db, "CHECK_OUT")] == ["Quarto 101 libertado - Rui\nJoão Caixa"]


async def test_a_till_closed(db, team):
    ctx = team
    session = await open_session(db, ctx["company"].id, ctx["pos"].id, ctx["cashier"], 1000)
    await close_session(db, ctx["company"].id, session.id, ctx["cashier"].id, closing_amount_counted=900,
                        closing_notes="Troco a mais")
    [message] = await _messages(db, "CAIXA_FECHADA")
    assert message.text == ("Caixa Teste fechada por João Caixa\nEsperado 1 000,00 Kz · contado 900,00 Kz\n"
                            "Diferença -100,00 Kz - Troco a mais")


async def test_low_stock_once_at_the_crossing(db, team):
    ctx = team
    product = await _product(db, ctx, stock=12, minimum=10)
    for quantity in (1, 2, 1):  # 12 -> 11 (still above), 11 -> 9 (crossing), 9 -> 8 (already under)
        await create_invoice(db, ctx["company"].id, ctx["activity"].id, None, "FACTURA_RECIBO",
                             [{"product_id": product.id, "quantity": quantity}], payment_method_id=ctx["pm_numerario"].id)
    assert [m.text for m in await _messages(db, "STOCK_BAIXO")] == ["Donut: 9 UN (mínimo 10) - Atividade - Ponto de Venda"]
