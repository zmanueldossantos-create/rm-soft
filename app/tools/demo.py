"""
The demonstration company - Padaria Sol de Luanda - filled with a month of realistic activity, for the site's screenshots
and for showing RM SOFT to a prospect.

    python -m app.tools.demo              creates it (refused when it already exists)
    python -m app.tools.demo --recriar    deletes it (only it: its NIF is DEMO_NIF) and creates it again, with dates
                                          up to today

What it holds: 25 articles with a picture (bread, pastries, snacks, drinks, groceries), the stock produced or bought from
2 suppliers (purchase invoices), 5 customers, about 30 days of sales (Faturas-Recibo at the counter, some Faturas to
customers - a few still unpaid), and today a till open with its first sales. Every document goes through the same
services as the screens (numbering, VAT, stock, AGT queue) - nothing is written around them.

Accounts (password Demo@2026): GESTOR +244923999001, CAIXA +244923999002. In SaaS mode: demo.<domain>.
Run it on a development machine or the RM SOFT platform - never on a client's server.
"""
import asyncio
import random
import shutil
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import delete, select

DEMO_NIF = "5000999001"
DEMO_NAME = "Padaria Sol de Luanda, Lda"
DEMO_SHORT = "Padaria Sol"
PASSWORD = "Demo@2026"
GESTOR = ("Ana Domingos", "+244923999001")
CAIXA = ("João Caixa", "+244923999002")
HISTORY_DAYS = 30
IMAGES = Path(__file__).resolve().parent / "demo_imagens"


@dataclass
class Article:
    code: str
    name: str
    category: str
    price: float
    cost: float
    vat: str  # NOR | RED
    weight: float  # how often it is sold (relative)
    bought: bool = False  # True: bought from a supplier (purchase invoice); False: made in the bakery
    stock: bool = True  # False: prepared at the counter, no stock (coffee...)
    barcode: str | None = None


ARTICLES = [
    Article("PAO01", "Pão de água", "Pão", 50, 22, "RED", 10),
    Article("PAO02", "Pão de forma", "Pão", 650, 380, "RED", 3),
    Article("PAO03", "Broa de milho", "Pão", 300, 150, "RED", 2),
    Article("PAO04", "Pão com chouriço", "Pão", 450, 220, "NOR", 3),
    Article("PAS01", "Croissant", "Pastelaria", 350, 150, "NOR", 5),
    Article("PAS02", "Pastel de nata", "Pastelaria", 300, 120, "NOR", 5),
    Article("PAS03", "Bolo de chocolate (fatia)", "Pastelaria", 800, 300, "NOR", 3),
    Article("PAS04", "Queque", "Pastelaria", 250, 90, "NOR", 4),
    Article("PAS05", "Donut", "Pastelaria", 400, 150, "NOR", 4),
    Article("PAS06", "Bolo de aniversário 1 kg", "Pastelaria", 12000, 5000, "NOR", 0.3),
    Article("SAL01", "Sandes mista", "Salgados", 900, 420, "NOR", 4),
    Article("SAL02", "Empada de frango", "Salgados", 500, 200, "NOR", 3),
    Article("SAL03", "Pizza (fatia)", "Salgados", 1000, 450, "NOR", 3),
    Article("SAL04", "Rissol de camarão", "Salgados", 350, 140, "NOR", 3),
    Article("BEB01", "Café expresso", "Bebidas", 300, 80, "NOR", 7, stock=False),
    Article("BEB02", "Galão", "Bebidas", 500, 150, "NOR", 3, stock=False),
    Article("BEB03", "Sumo natural de laranja", "Bebidas", 700, 250, "NOR", 3, stock=False),
    Article("BEB04", "Água mineral 0,5 L", "Bebidas", 200, 90, "NOR", 5, bought=True, barcode="5609990000041"),
    Article("BEB05", "Refrigerante lata 33 cl", "Bebidas", 450, 250, "NOR", 5, bought=True, barcode="5609990000058"),
    Article("BEB06", "Chá", "Bebidas", 250, 60, "NOR", 2, stock=False),
    Article("MER01", "Leite UHT meio-gordo 1 L", "Mercearia", 900, 620, "RED", 2, bought=True, barcode="5609990000102"),
    Article("MER02", "Ovos (dúzia)", "Mercearia", 1800, 1300, "RED", 1, bought=True, barcode="5609990000119"),
    Article("MER03", "Manteiga 250 g", "Mercearia", 1500, 1050, "NOR", 1, bought=True, barcode="5609990000126"),
    Article("MER04", "Iogurte natural", "Mercearia", 350, 220, "NOR", 2, bought=True, barcode="5609990000133"),
    Article("MER05", "Mel 500 g", "Mercearia", 3500, 2400, "NOR", 0.5, bought=True, barcode="5609990000140"),
]

SUPPLIERS = {
    "Bebidas": ("Distribuidora Kwanza Bebidas, Lda", "5000999201"),
    "Mercearia": ("Armazéns Mutamba, Lda", "5000999202"),
}

CUSTOMERS = [
    ("Hotel Baía Azul, Lda", "5000999101"),
    ("Escola Primária Esperança", "5000999102"),
    ("Café Kianda, Lda", "5000999103"),
    ("Restaurante Mar e Sol, Lda", "5000999104"),
    ("Construções Kwanza, Lda", "5000999105"),
]


def say(text: str) -> None:
    print(text, flush=True)


class DemoError(Exception):
    """The demonstration cannot be made here - the message says why (PT-PT)."""


LOW_STOCK = {"PAS05", "MER03"}  # left under their minimum: the alerts of the Painel and the Stock have something to show


def _left_over(art: Article, rnd: random.Random) -> int:
    """What is still in stock today, once the month's sales are made."""
    if art.code in LOW_STOCK:
        return rnd.randint(3, 6)
    if art.price > 5000:
        return rnd.randint(2, 4)
    return rnd.randint(15, 40)


# ------------------------------------------------------------------------------------------------------ the catalog

async def _catalog(db):
    """What the platform must already have: Padaria module, units, payment methods, document types FT and FR."""
    from app.models.document_type import DocumentType
    from app.models.legal_vat_rate import LegalVatRate
    from app.models.module import Module
    from app.models.payment_method_catalog import PaymentMethodCatalog
    from app.models.plan import Plan
    from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog

    module = (await db.execute(select(Module).where(Module.name == "Padaria"))).scalar_one_or_none()
    unit = (await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.code == "UN"))).scalar_one_or_none()
    methods = {m.code: m for m in (await db.execute(select(PaymentMethodCatalog))).scalars().all()}
    doc_codes = set((await db.execute(select(DocumentType.code))).scalars().all())
    missing = []
    if module is None:
        missing.append("o módulo Padaria")
    if unit is None:
        missing.append("a unidade UN (Configurações > Unidades)")
    if "NU" not in methods:
        missing.append("o meio de pagamento NU (Numerário)")
    missing += [f"o tipo de documento {code}" for code in ("FT", "FR") if code not in doc_codes]
    if missing:
        raise DemoError("Falta no catálogo da plataforma: " + ", ".join(missing))
    legal = {r.tax_category: r for r in (await db.execute(select(LegalVatRate))).scalars().all()}
    plan = (await db.execute(select(Plan).where(Plan.name == "Profissional", Plan.is_active.is_(True)))).scalar_one_or_none()
    from app.models.fiscal_regime import FiscalRegime
    regimes = (await db.execute(select(FiscalRegime).order_by(FiscalRegime.name))).scalars().all()
    regime = next((r for r in regimes if "geral" in r.name.lower()), regimes[0] if regimes else None)
    return module, unit, methods, legal, plan, regime


# --------------------------------------------------------------------------------------------------- delete it again

async def purge(db) -> bool:
    """Deletes the demonstration company and everything that belongs to it (only the company with DEMO_NIF)."""
    from app.models.company import Company
    from app.models.product import Product
    from app.services.company_backup_service import _tables

    company = (await db.execute(select(Company).where(Company.nif == DEMO_NIF))).scalar_one_or_none()
    if company is None:
        return False
    company_id = company.id
    images = (await db.execute(select(Product.image_path).where(Product.company_id == company_id))).scalars().all()
    owned, children, _ = _tables()
    owned_names = {t.name for t in owned}
    # the lines first (no company_id: found through their parent row), then the company's tables, last ones first
    for table in reversed(children):
        for column in table.c:
            for fk in column.foreign_keys:
                parent = fk.column.table
                if parent.name in owned_names:
                    ids = select(parent.c.id).where(parent.c.company_id == company_id)
                    await db.execute(delete(table).where(column.in_(ids)))
    for table in reversed(owned):
        await db.execute(delete(table).where(table.c.company_id == company_id))
    await db.execute(delete(Company.__table__).where(Company.__table__.c.id == company_id))
    await db.commit()
    for path in [*images, f"/uploads/logos/{company_id}.png"]:
        if path:
            Path(path.lstrip("/")).unlink(missing_ok=True)
    return True


# ----------------------------------------------------------------------------------------------------------- build it

async def build(db, today: date) -> dict:
    from app.models.company_payment_method_preference import CompanyPaymentMethodPreference
    from app.models.fiscal_period import FiscalPeriod
    from app.models.fiscal_year import FiscalYear
    from app.models.product import Product
    from app.models.user import User
    from app.models.vat import VAT
    from app.services.activity_service import create_activity
    from app.services.auth_service import create_user
    from app.services.cash_session_service import open_session
    from app.services.company_service import create_company
    from app.services.customer_service import create_customer
    from app.services.fiscal_period_service import close_fiscal_period, open_fiscal_period
    from app.services.invoice_service import create_invoice
    from app.services.point_of_sale_service import list_points_of_sale
    from app.services.product_category_service import create_product_category
    from app.services.product_service import create_product
    from app.services.purchase_invoice_service import register_purchase_invoice
    from app.services.stock_service import receive_stock, update_average_cost
    from app.services.supplier_service import create_supplier
    from app.services.user_cash_point_access_service import assign_user_to_cash_point

    rnd = random.Random(2026)
    module, unit, methods, legal, plan, regime = await _catalog(db)

    say("1/7 Empresa")
    company = await create_company(
        db, name=DEMO_NAME, short_name=DEMO_SHORT, nif=DEMO_NIF, email="demo@rmsystem.co.ao",
        phone_number="+244923999000", gestor_full_name=GESTOR[0], gestor_phone_number=GESTOR[1], gestor_password=PASSWORD,
        address="Rua Rainha Ginga, 45", city="Luanda", module_ids=[module.id], subdomain="demo",
        commercial_registration_number="0457/2021", fiscal_regime_id=regime.id if regime else None,
        plan_id=plan.id if plan else None, billing="ANUAL", contract_start=today - timedelta(days=HISTORY_DAYS + 5),
    )
    cid = company.id
    logo = Path("uploads") / "logos"
    logo.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(IMAGES / "logo.png", logo / f"{cid}.png")
    company.logo_path = f"/uploads/logos/{cid}.png"
    gestor = (await db.execute(select(User).where(User.company_id == cid))).scalar_one()
    activity = await create_activity(db, cid, module.id, "Padaria")
    pos = (await list_points_of_sale(db, cid, activity.id))[0]
    caixa = await create_user(db, cid, CAIXA[0], CAIXA[1], PASSWORD, "CAIXA")
    await assign_user_to_cash_point(db, cid, caixa.id, pos.id)
    card = methods.get("CD")
    if card is not None:  # Multicaixa at the till, next to cash
        db.add(CompanyPaymentMethodPreference(company_id=cid, payment_method_id=card.id, available_at_pos=True))
    vats = {v.tax_category: v for v in (await db.execute(select(VAT).where(VAT.company_id == cid))).scalars().all()}

    # the months of the history: the first one opened directly (a company starting then), each closed in turn
    start = max(today - timedelta(days=HISTORY_DAYS), date(today.year, 1, 1))
    year = FiscalYear(company_id=cid, year=today.year, status="ABERTO")
    db.add(year)
    await db.flush()
    db.add(FiscalPeriod(company_id=cid, fiscal_year_id=year.id, month=start.month, status="ABERTO"))
    await db.commit()

    say("2/7 Artigos")
    categories = {}
    products = {}
    for art in ARTICLES:
        if art.category not in categories:
            categories[art.category] = (await create_product_category(db, cid, art.category)).id
        vat = vats.get(art.vat) or vats["NOR"]
        product = await create_product(
            db, cid, code=art.code, name=art.name, barcode=art.barcode, vat_id=vat.id, price=art.price,
            min_stock_threshold=(1 if art.price > 5000 else 10) if art.stock else 0, unit_of_measure_id=unit.id, category_id=categories[art.category],
            purchase_price=art.cost, managed_by_stock=art.stock,
        )
        image = IMAGES / f"{art.code}.png"
        if image.exists():
            folder = Path("uploads") / "products"
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(image, folder / f"{product.id}.png")
            product.image_path = f"/uploads/products/{product.id}.png"
        products[art.code] = product
    await db.commit()

    # how much of each article the month will sell, to put that much (and some more) in stock
    days = [start + timedelta(days=i) for i in range((today - start).days + 1)]
    plan_sales = []  # (day, [(code, qty)], customer index or None, method code, kind)
    sold = {art.code: 0 for art in ARTICLES}
    weights = [art.weight for art in ARTICLES]
    for day in days:
        count = rnd.randint(7, 10) if day.weekday() >= 5 else rnd.randint(4, 7)
        if day == today:
            count = 6
        for _ in range(count):
            basket = {}
            for art in rnd.choices(ARTICLES, weights=weights, k=rnd.randint(1, 4)):
                qty = rnd.randint(2, 12) if art.code == "PAO01" else 1 if art.price > 5000 else rnd.randint(1, 3)
                basket[art.code] = basket.get(art.code, 0) + qty
            customer = rnd.randrange(len(CUSTOMERS)) if day != today and rnd.random() < 0.18 else None
            if customer is not None:  # an order from a customer: bigger
                basket = {code: qty * rnd.randint(2, 4) for code, qty in basket.items()}
            method = "CD" if card is not None and rnd.random() < 0.4 else "NU"
            kind = "FACTURA" if customer is not None and rnd.random() < 0.6 else "FACTURA_RECIBO"
            plan_sales.append((day, list(basket.items()), customer, method, kind))
            for code, qty in basket.items():
                sold[code] += qty

    say("3/7 Stock: produção e compras")
    for art in ARTICLES:
        if not art.stock or art.bought:
            continue
        product = products[art.code]
        quantity = sold[art.code] + _left_over(art, rnd)
        await update_average_cost(db, cid, product, quantity, art.cost)
        await receive_stock(db, cid, product.id, quantity, reason="Produção da padaria", warehouse_id=activity.warehouse_id)
    suppliers = {}
    for category, (name, nif) in SUPPLIERS.items():
        suppliers[category] = await create_supplier(db, cid, name, nif=nif, phone_number=None)
    for number, (category, supplier) in enumerate(suppliers.items(), start=1):
        lines = []
        for art in ARTICLES:
            if art.bought and art.category == category:
                quantity = sold[art.code] + _left_over(art, rnd)
                lines.append({"product_id": products[art.code].id, "description": art.name, "quantity": quantity,
                              "unit_price": art.cost, "legal_vat_rate_id": legal[art.vat].id if art.vat in legal else None})
        await register_purchase_invoice(
            db, cid, gestor.id, supplier.id, f"FT {today.year}/{700 + number}", start, lines,
            stock_entry=True, warehouse_id=activity.warehouse_id,
        )

    say("4/7 Clientes")
    customers = [await create_customer(db, cid, name, nif, legal_person_type="JURIDICA") for name, nif in CUSTOMERS]

    say(f"5/7 Vendas de {start.strftime('%d/%m')} a {(today - timedelta(days=1)).strftime('%d/%m')}")
    session = None
    issued = 0
    current_month = start.month
    for day, basket, customer, method, kind in plan_sales:
        if day.month != current_month:  # a new month: the previous one is closed, the next one opened
            previous = (await db.execute(select(FiscalPeriod).where(
                FiscalPeriod.fiscal_year_id == year.id, FiscalPeriod.month == current_month))).scalar_one()
            await close_fiscal_period(db, cid, previous.id)
            await open_fiscal_period(db, cid, year.id)
            current_month = day.month
        if day == today and session is None:
            say("6/7 Hoje: caixa aberta e primeiras vendas")
            session = await open_session(db, cid, pos.id, caixa, opening_amount=5000)
        await create_invoice(
            db, cid, activity.id, customers[customer].id if customer is not None else None, kind,
            [{"product_id": products[code].id, "quantity": qty} for code, qty in basket],
            business_date=day, payment_method_id=methods[method].id,
            cash_session_id=session.id if session is not None and kind == "FACTURA_RECIBO" else None,
            due_date=day + timedelta(days=30) if kind == "FACTURA" else None,
        )
        issued += 1

    say("7/7 Pronto")
    return {"company": company, "invoices": issued, "start": start}


async def main() -> None:
    from app.core.database import AsyncSessionLocal
    recreate = "--recriar" in sys.argv
    async with AsyncSessionLocal() as db:
        from app.models.company import Company
        exists = (await db.execute(select(Company.id).where(Company.nif == DEMO_NIF))).first() is not None
        if exists and not recreate:
            say(f"A empresa de demonstração ({DEMO_NAME}) já existe. Para a criar de novo: python -m app.tools.demo --recriar")
            return
        if exists:
            say("A apagar a demonstração anterior...")
            await purge(db)
        try:
            result = await build(db, date.today())
        except DemoError as e:
            say(f"ERRO: {e}")
            sys.exit(1)
    say("")
    say(f"Empresa: {DEMO_NAME} (NIF {DEMO_NIF}) - {result['invoices']} documentos desde {result['start'].strftime('%d/%m/%Y')}")
    say(f"GESTOR: {GESTOR[1]}   CAIXA: {CAIXA[1]}   palavra-passe: {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
