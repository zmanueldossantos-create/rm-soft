"""
Contabilidade - the stock in the inventário permanente: a purchase's goods into the stock (its automatic entry EA:
the stock debited, the purchases credited), then, once the day is over, one entry per warehouse and day - the cost of
the sales, the losses, the inventory surplus; nothing in the inventário intermitente.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.fiscal_regime import FiscalRegime
from app.models.journal import JournalEntry
from app.models.movement_type import MovementDirection, MovementType
from app.models.product import Product, ProductType
from app.models.supplier import Supplier
from app.services import accounting_integration_service as integration
from app.services.account_mapping_service import set_inventory_system, set_mapping
from app.services.chart_of_accounts_service import create_account, start_chart
from app.services.invoice_service import create_invoice
from app.services.journal_service import get_entry
from app.services.purchase_invoice_service import register_purchase_invoice
from app.services.stock_service import adjust_stock, record_stock_loss
from tests.test_purchase_invoices import _line, _rates


async def _entries(db, company_id, kind):
    ids = (await db.execute(select(JournalEntry.id).where(JournalEntry.source_kind == kind)
                            .order_by(JournalEntry.created_at))).scalars().all()
    out = []
    for entry_id in ids:
        entry = await get_entry(db, company_id, entry_id)
        out.append(sorted((l["account_code"], float(l["debit"]), float(l["credit"])) for l in entry["lines"]))
    return out


async def _setup(db, ctx, monkeypatch):
    company = ctx["company"]
    company_id = company.id
    regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == company.fiscal_regime_id))).scalar_one()
    regime.input_vat_deductible_pct = 100
    supplier = Supplier(company_id=company_id, name="Grossista Lda", nif="5000111222")
    water = Product(company_id=company_id, code="AGUA", name="Água", vat_id=ctx["vat_nor"].id, price=500,
                    min_stock_threshold=0, product_type=ProductType.BEM)
    db.add_all([supplier, water, MovementType(code="EA", name="Entrada automática", direction=MovementDirection.ENTRADA, is_auto=True)])
    nor, _ise = await _rates(db)
    await db.commit()
    await start_chart(db, company_id, "PGC")
    # 26 and 71 have sub-accounts in the PGC: the accountant chooses a last-level one
    goods = await create_account(db, company_id, "26.1", "Mercadorias em armazém")
    cost = await create_account(db, company_id, "71.6", "Mercadorias")
    await set_mapping(db, company_id, "STOCK_GOODS", goods.id)
    await set_mapping(db, company_id, "COST_OF_SALES", cost.id)
    monkeypatch.setattr(integration, "_today", lambda: date.today() + timedelta(days=1))  # today's stock: over
    warehouse_id = ctx["activity_warehouse"].id
    await register_purchase_invoice(db, company_id, ctx["gestor"].id, supplier.id, "FT A/1", date.today(),
                                    [_line(nor, product_id=water.id)], stock_entry=True, warehouse_id=warehouse_id)  # 10 x 100
    return company_id, water.id, warehouse_id


@pytest.mark.asyncio
async def test_the_stock_in_the_inventario_permanente(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id, water_id, warehouse_id = await _setup(db, ctx, monkeypatch)
    await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                         lines_input=[{"product_id": water_id, "quantity": 4}])
    await record_stock_loss(db, company_id, warehouse_id, water_id, 1, "QUEBRA", "Garrafa partida")
    await adjust_stock(db, company_id, warehouse_id, water_id, 7, "Contagem")  # 5 -> 7: a surplus of 2

    result = await integration.integrate_company(db, company_id)
    assert result["pending"] == 0
    assert await _entries(db, company_id, "STOCK_DOCUMENT") == [[("21.2", 0.0, 1000.0), ("26.1", 1000.0, 0.0)]]
    [day] = await _entries(db, company_id, "STOCK_DAY")
    # sold 4 (400 to the cost of sales), lost 1 (100), a surplus of 2 (200)
    assert day == sorted([("71.6", 400.0, 0.0), ("26.1", 0.0, 400.0), ("78.4.1", 100.0, 0.0), ("26.1", 0.0, 100.0),
                          ("26.1", 200.0, 0.0), ("68.4.1", 0.0, 200.0)])
    assert (await integration.integrate_company(db, company_id))["posted"] == 0  # once per day and warehouse


@pytest.mark.asyncio
async def test_the_day_waits_while_it_is_not_over_and_nothing_in_the_intermitente(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id, water_id, _warehouse = await _setup(db, ctx, monkeypatch)
    await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                         lines_input=[{"product_id": water_id, "quantity": 4}])
    monkeypatch.setattr(integration, "_today", lambda: date.today())  # today is not over yet
    await integration.integrate_company(db, company_id)
    assert await _entries(db, company_id, "STOCK_DAY") == []
    await set_inventory_system(db, company_id, "INTERMITENTE")
    monkeypatch.setattr(integration, "_today", lambda: date.today() + timedelta(days=1))
    await integration.integrate_company(db, company_id)
    assert await _entries(db, company_id, "STOCK_DAY") == []
    assert len(await _entries(db, company_id, "STOCK_DOCUMENT")) == 1  # posted before the change


@pytest.mark.asyncio
async def test_a_sale_written_after_its_day_was_posted_gets_an_entry_of_its_own(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id, water_id, _warehouse = await _setup(db, ctx, monkeypatch)
    await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                         lines_input=[{"product_id": water_id, "quantity": 4}])
    await integration.integrate_company(db, company_id)
    await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                         lines_input=[{"product_id": water_id, "quantity": 2}])  # the same day, already posted
    await integration.integrate_company(db, company_id)
    assert await _entries(db, company_id, "STOCK_DAY") == [
        [("26.1", 0.0, 400.0), ("71.6", 400.0, 0.0)], [("26.1", 0.0, 200.0), ("71.6", 200.0, 0.0)]]
    assert (await integration.integration_status(db, company_id))["waiting"] == 0


@pytest.mark.asyncio
async def test_today_in_modo_formacao_and_its_estorno_once_left_out(db, company_with_essentials, monkeypatch):
    """A demonstration in one go: today's stock posted at once (Modo formação only), the rest of the day once it is
    over; the Modo formação documents no longer in the accounting: the day's entry reversed."""
    from app.models.company import Company
    ctx = company_with_essentials
    company_id, water_id, _warehouse = await _setup(db, ctx, monkeypatch)
    monkeypatch.setattr(integration, "_today", lambda: date.today())  # today is not over
    with pytest.raises(integration.IntegrationError, match="Modo formação"):
        await integration.integrate_today(db, company_id)
    (await db.get(Company, company_id)).training_mode = True
    await db.commit()
    await integration.set_include_training(db, company_id, True)
    await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                         lines_input=[{"product_id": water_id, "quantity": 4}])
    await integration.integrate_company(db, company_id)
    assert await _entries(db, company_id, "STOCK_DAY") == []  # the loop waits for the day's end
    await integration.integrate_today(db, company_id)
    assert await _entries(db, company_id, "STOCK_DAY") == [[("26.1", 0.0, 400.0), ("71.6", 400.0, 0.0)]]
    await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                         lines_input=[{"product_id": water_id, "quantity": 1}])
    monkeypatch.setattr(integration, "_today", lambda: date.today() + timedelta(days=1))  # the day is over: its rest
    await integration.integrate_company(db, company_id)
    assert len(await _entries(db, company_id, "STOCK_DAY")) == 2

    await integration.set_include_training(db, company_id, False)
    await integration.integrate_company(db, company_id)
    entries = (await db.execute(select(JournalEntry).where(JournalEntry.description.like("Estorno de OD%")))).scalars().all()
    assert len(entries) == 2  # both days' entries reversed, nothing posted again (only Modo formação sales)
    assert (await integration.integrate_company(db, company_id))["posted"] == 0
    assert len(await _entries(db, company_id, "STOCK_DOCUMENT")) == 1  # the purchase's goods stay
