"""
Contabilidade - the entries the system makes from the documents (integração contabilística), with the accounts of
«Contas por operação» and the sub-accounts it made (app.services.account_mapping_service).

Sales documents (FT, FR, ND, NC, RC), dated from AccountingSettings.integration_start on, Modo formação left out:
  - FT / ND (journal VND): the customer debited with the total; the sales credited net of VAT - goods, products made by
    the company (a product with a recipe) or services, each to its account -; the VAT to «IVA liquidado»;
  - NC: the same reversed, the net on «Devoluções»;
  - FR: the FT, then its payment in the same entry: the till (cash) or the bank account (the other methods) debited,
    the customer credited; the withholding kept by the customer to «Retenção na fonte sofrida»;
  - RC (journal CX when paid in cash, BCO otherwise): the till or bank debited, the withholding, the customer credited;
  - a refund (a negative payment of an NC): the till or bank credited, the customer debited.
Purchases (journal CMP), from their document date (or the first day of the period they were booked in, a late one):
  - the supplier credited with the total; each line's cost (net + the VAT not deductible) debited by kind - goods, raw
    materials, services and consumables (75.2), fixed assets (the deductible VAT type MFI) -; the deductible VAT to
    «IVA dedutível»; a supplier's credit note: the same reversed.
Supplier payments (journal CX in cash, BCO otherwise): the supplier debited, the till or the bank credited. A FR / TV
of a supplier is paid on issue: its payment is one of these, posted as such.
A purchase or a payment cancelled after its entry: the estorno of that entry, on the cancellation day.

The customer: its sub-account; a final consumer or no customer: «Consumidor final»; the company keeping no
sub-account per customer: the parent account (national or foreign) itself. The supplier: its sub-account, or the
suppliers' parent account itself. The till: the sub-account of the caixa of
the cash session (the activity's default caixa otherwise); the bank: the sub-account of the document's bank account.

The entry is posted at once (numbered in its journal), linked to its document, never changed by hand (an estorno only).
A document that cannot be posted - an account not set, a period closed... - waits in PendingIntegration with the
reason, and is tried again each round (integration_loop, every minute) or at once from the screen.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.data.account_operations import OPERATIONS_BY_KEY
from app.models.account import Account, AccountingSettings, AccountLink, AccountMapping
from app.models.cash_session import CashSession
from app.models.country import Country
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceType
from app.models.invoice_line import InvoiceLine
from app.models.journal import Journal, JournalEntry, PendingIntegration
from app.models.payment import Payment
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.point_of_sale import PointOfSale
from app.models.product import Product, ProductType
from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceLine, PurchaseInvoiceStatus
from app.models.recipe_ingredient import RecipeIngredient
from app.models.supplier import Supplier
from app.models.supplier_payment import SupplierPayment, SupplierPaymentStatus
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
from app.services.journal_service import JournalError, save_entry

log = logging.getLogger(__name__)

SOURCE_INVOICE = "INVOICE"
SOURCE_PURCHASE = "PURCHASE"
SOURCE_SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT"
LUANDA = ZoneInfo("Africa/Luanda")
POSTED_TYPES = (InvoiceType.FACTURA, InvoiceType.FACTURA_RECIBO, InvoiceType.NOTA_DEBITO, InvoiceType.NOTA_CREDITO,
                InvoiceType.RECIBO)
TRAINING = "FORMACAO"
BATCH = 300
LOOP_SECONDS = 60
ZERO = Decimal("0.00")


class IntegrationError(Exception):
    """Why a document cannot be posted yet (PT-PT, shown in «Por integrar»)."""


@dataclass
class _Context:
    settings: AccountingSettings
    accounts: dict[uuid.UUID, Account]
    mappings: dict[str, Account]
    links: dict[tuple[str, uuid.UUID], Account]
    journals: dict[str, Journal]


async def _context(db: AsyncSession, company_id: uuid.UUID, settings: AccountingSettings) -> _Context:
    accounts = {a.id: a for a in (await db.execute(select(Account).where(Account.company_id == company_id))).scalars().all()}
    mappings = {m.operation: accounts[m.account_id] for m in (await db.execute(
        select(AccountMapping).where(AccountMapping.company_id == company_id))).scalars().all() if m.account_id in accounts}
    links = {(l.entity_kind, l.entity_id): accounts[l.account_id] for l in (await db.execute(
        select(AccountLink).where(AccountLink.company_id == company_id))).scalars().all() if l.account_id in accounts}
    journals = {j.code: j for j in (await db.execute(select(Journal).where(Journal.company_id == company_id))).scalars().all()}
    return _Context(settings, accounts, mappings, links, journals)


def _mapped(ctx: _Context, key: str) -> Account:
    account = ctx.mappings.get(key)
    if account is None:
        raise IntegrationError(f"Defina a conta de «{OPERATIONS_BY_KEY[key].label}» em Contas por operação")
    return account


KIND_LABEL = {InvoiceType.FACTURA: "Fatura", InvoiceType.FACTURA_RECIBO: "Fatura-recibo", InvoiceType.NOTA_DEBITO: "Nota de débito",
              InvoiceType.NOTA_CREDITO: "Nota de crédito", InvoiceType.RECIBO: "Recibo"}


def _label(invoice: Invoice) -> str:
    code = DOC_CODE_BY_INVOICE_TYPE.get(invoice.invoice_type.value, invoice.invoice_type.value)
    return f"{code} {invoice.series}/{invoice.number}"


async def _customer(db: AsyncSession, ctx: _Context, invoice: Invoice) -> tuple[Account, str]:
    customer = await db.get(Customer, invoice.customer_id) if invoice.customer_id else None
    if customer is not None and not customer.is_final_consumer:
        if ctx.settings.subaccount_per_customer:
            account = ctx.links.get(("CUSTOMER", customer.id))
            if account is None:
                raise IntegrationError(f"O cliente {customer.name} ainda não tem subconta - defina a conta-mãe dos "
                                       "clientes em Contas por operação")
            return account, customer.name
        country = (await db.execute(select(Country.code).where(Country.id == customer.country_id))).scalar_one_or_none() \
            if customer.country_id else None
        foreign = country is not None and country.upper() != "AO"
        return _mapped(ctx, "PARENT_CUSTOMERS_FOREIGN" if foreign else "PARENT_CUSTOMERS_NATIONAL"), customer.name
    if ctx.settings.subaccount_per_customer:
        return _mapped(ctx, "CUSTOMERS_GENERIC"), "Consumidor final"
    return ctx.mappings.get("CUSTOMERS_GENERIC") or _mapped(ctx, "PARENT_CUSTOMERS_NATIONAL"), "Consumidor final"


def _till(ctx: _Context, pos_id: uuid.UUID | None) -> Account:
    account = ctx.links.get(("TILL", pos_id)) if pos_id else None
    if account is None:
        raise IntegrationError("A caixa do pagamento ainda não tem subconta - defina a conta-mãe das caixas em "
                               "Contas por operação")
    return account


def _money_account(ctx: _Context, method: PaymentMethodCatalog, bank_account_id: uuid.UUID | None) -> Account:
    """The account of a payment that is not cash: its bank account, or «Outros meios de pagamento»."""
    if method.uses_bank_account:
        if bank_account_id is None:
            raise IntegrationError(f"O documento não indica a conta bancária do pagamento ({method.name})")
        account = ctx.links.get(("BANK", bank_account_id))
        if account is None:
            raise IntegrationError("A conta bancária do pagamento ainda não tem subconta - defina a conta-mãe dos "
                                   "bancos em Contas por operação")
        return account
    account = ctx.mappings.get("OTHER_MEANS")  # the other methods: the account the company chose for them
    if account is None:
        raise IntegrationError(f"O meio de pagamento «{method.name}» não leva o dinheiro a uma caixa nem a um banco - "
                               "defina a conta de «Outros meios de pagamento» em Contas por operação")
    return account


async def _treasury(db: AsyncSession, ctx: _Context, invoice: Invoice, method: PaymentMethodCatalog) -> Account:
    """Where the money of one payment of a sales document is: the caixa (cash) or the bank account."""
    if method.is_cash:
        pos_id = None
        if invoice.cash_session_id:
            pos_id = (await db.execute(select(CashSession.pos_id).where(CashSession.id == invoice.cash_session_id))).scalar_one_or_none()
        if pos_id is None:  # cash taken outside a cash session: the activity's default caixa
            pos_id = (await db.execute(select(PointOfSale.id).where(
                PointOfSale.activity_id == invoice.activity_id, PointOfSale.is_default.is_(True)))).scalar_one_or_none()
        return _till(ctx, pos_id)
    return _money_account(ctx, method, invoice.bank_account_id)


async def _sales(db: AsyncSession, ctx: _Context, invoice: Invoice) -> list[tuple[Account, str, Decimal]]:
    """The net of the document split by kind of sale: [(account, label, amount)], the total = invoice.subtotal."""
    rows = (await db.execute(
        select(InvoiceLine.line_subtotal, InvoiceLine.service_id, Product.id, Product.product_type)
        .outerjoin(Product, Product.id == InvoiceLine.product_id).where(InvoiceLine.invoice_id == invoice.id)
    )).all()
    produced = set((await db.execute(select(RecipeIngredient.finished_product_id).where(
        RecipeIngredient.finished_product_id.in_([r[2] for r in rows if r[2]])))).scalars().all()) if rows else set()
    buckets: dict[str, Decimal] = {}
    for subtotal, service_id, product_id, product_type in rows:
        if service_id or product_type == ProductType.SERVICO:
            key = "SALES_SERVICES"
        elif product_id in produced:
            key = "SALES_PRODUCTS"
        else:
            key = "SALES_GOODS"
        buckets[key] = buckets.get(key, ZERO) + Decimal(str(subtotal))
    net = Decimal(str(invoice.subtotal))
    if not buckets:
        buckets["SALES_GOODS"] = ZERO
    # the document's net is the reference (a global discount, roundings): the difference on the largest kind
    largest = max(buckets, key=lambda k: buckets[k])
    buckets[largest] += net - sum(buckets.values())
    if invoice.invoice_type == InvoiceType.NOTA_CREDITO:
        return [(_mapped(ctx, "SALES_RETURNS"), OPERATIONS_BY_KEY["SALES_RETURNS"].label, net)]
    return [(_mapped(ctx, key), OPERATIONS_BY_KEY[key].label, amount) for key, amount in buckets.items() if amount]


def _adder(lines: list[dict]):
    """add(account, description, amount, debit): one line of an entry - a negative amount goes on the other side, a
    zero one is left out."""
    def add(account: Account, description: str, amount: Decimal, debit: bool) -> None:
        amount = amount.quantize(Decimal("0.01"))
        if amount < 0:
            amount, debit = -amount, not debit
        if amount:
            lines.append({"account_id": account.id, "description": description[:200],
                          "debit": amount if debit else ZERO, "credit": ZERO if debit else amount})
    return add


async def build_invoice_entry(db: AsyncSession, ctx: _Context, invoice: Invoice) -> tuple[str, list[dict]]:
    """(journal code, lines) of a sales document - IntegrationError when an account is missing."""
    customer, customer_name = await _customer(db, ctx, invoice)
    lines: list[dict] = []
    add = _adder(lines)
    kind = invoice.invoice_type
    if kind != InvoiceType.RECIBO:
        total, vat = Decimal(str(invoice.total)), Decimal(str(invoice.vat_total))
        if total != Decimal(str(invoice.subtotal)) + vat:
            raise IntegrationError("O documento tem outros impostos além do IVA (IEC, Selo) - ainda não integrados")
        sale = kind != InvoiceType.NOTA_CREDITO  # an NC is the same entry reversed
        add(customer, customer_name, total, debit=sale)
        for account, label, amount in await _sales(db, ctx, invoice):
            add(account, label, amount, debit=not sale)
        add(_mapped(ctx, "VAT_OUTPUT"), OPERATIONS_BY_KEY["VAT_OUTPUT"].label, vat, debit=not sale)

    payments = (await db.execute(
        select(Payment.amount, PaymentMethodCatalog).join(PaymentMethodCatalog, PaymentMethodCatalog.id == Payment.payment_method_id)
        .where(Payment.invoice_id == invoice.id).order_by(Payment.created_at)
    )).all()
    all_cash = bool(payments)
    for amount, method in payments:
        amount = Decimal(str(amount))
        all_cash = all_cash and method.is_cash
        add(await _treasury(db, ctx, invoice, method), method.short_label or method.name, amount, debit=True)
        add(customer, customer_name, amount, debit=False)
    retention = Decimal(str(invoice.retention_total or 0))
    if retention and kind in (InvoiceType.FACTURA_RECIBO, InvoiceType.RECIBO):
        add(_mapped(ctx, "WITHHOLDING_SUFFERED"), OPERATIONS_BY_KEY["WITHHOLDING_SUFFERED"].label, retention, debit=True)
        add(customer, customer_name, retention, debit=False)

    if kind == InvoiceType.RECIBO:
        return ("CX" if all_cash else "BCO"), lines
    return "VND", lines


# ---------- purchases and supplier payments ----------

async def _supplier(db: AsyncSession, ctx: _Context, supplier_id: uuid.UUID) -> tuple[Account, str]:
    supplier = await db.get(Supplier, supplier_id)
    if ctx.settings.subaccount_per_supplier:
        account = ctx.links.get(("SUPPLIER", supplier.id))
        if account is None:
            raise IntegrationError(f"O fornecedor {supplier.name} ainda não tem subconta - defina a conta-mãe dos "
                                   "fornecedores em Contas por operação")
        return account, supplier.name
    return _mapped(ctx, "PARENT_SUPPLIERS"), supplier.name


async def _purchase_date(db: AsyncSession, invoice: PurchaseInvoice) -> date:
    """The day of a purchase's entry: its document's date, or the first day of the period it was booked in when that
    is another month (a late invoice booked in the active period)."""
    month, year = (await db.execute(select(FiscalPeriod.month, FiscalYear.year).join(
        FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(FiscalPeriod.id == invoice.fiscal_period_id))).one()
    day = invoice.document_date
    return day if (day.year, day.month) == (year, month) else date(year, month, 1)


async def build_purchase_entry(db: AsyncSession, ctx: _Context, invoice: PurchaseInvoice) -> tuple[str, list[dict]]:
    """The supplier credited with the total; the cost of each line (net + the VAT not deductible) debited by kind -
    goods, raw materials, services and consumables, fixed assets (the deductible VAT type MFI) -; the deductible VAT to
    «IVA dedutível». A supplier's credit note: the same reversed."""
    supplier, supplier_name = await _supplier(db, ctx, invoice.supplier_id)
    rows = (await db.execute(
        select(PurchaseInvoiceLine.cost, PurchaseInvoiceLine.deductible_tax_type, PurchaseInvoiceLine.product_id,
               Product.is_raw_material, Product.product_type)
        .outerjoin(Product, Product.id == PurchaseInvoiceLine.product_id)
        .where(PurchaseInvoiceLine.purchase_invoice_id == invoice.id)
    )).all()
    buckets: dict[str, Decimal] = {}
    for cost, tax_type, product_id, raw, product_type in rows:
        if tax_type == "MFI":
            key = "PURCHASES_FIXED_ASSETS"
        elif product_id and product_type != ProductType.SERVICO:
            key = "PURCHASES_MATERIALS" if raw else "PURCHASES_GOODS"
        else:
            key = "PURCHASES_SERVICES"
        buckets[key] = buckets.get(key, ZERO) + Decimal(str(cost))
    total, deductible = Decimal(str(invoice.total)), Decimal(str(invoice.vat_deductible))
    if not buckets:
        buckets["PURCHASES_SERVICES"] = ZERO
    largest = max(buckets, key=lambda k: buckets[k])
    buckets[largest] += (total - deductible) - sum(buckets.values())  # the document's totals are the reference
    purchase = invoice.purchase_type != "NC"
    lines: list[dict] = []
    add = _adder(lines)
    for key, amount in buckets.items():
        add(_mapped(ctx, key), OPERATIONS_BY_KEY[key].label, amount, debit=purchase)
    add(_mapped(ctx, "VAT_DEDUCTIBLE"), OPERATIONS_BY_KEY["VAT_DEDUCTIBLE"].label, deductible, debit=purchase)
    add(supplier, supplier_name, total, debit=not purchase)
    return "CMP", lines


async def build_supplier_payment_entry(db: AsyncSession, ctx: _Context, payment: SupplierPayment) -> tuple[str, list[dict]]:
    """The supplier debited, the till (cash) or the bank account credited - journal CX or BCO."""
    supplier, supplier_name = await _supplier(db, ctx, payment.supplier_id)
    method = await db.get(PaymentMethodCatalog, payment.payment_method_id)
    money = _till(ctx, payment.pos_id) if method.is_cash else _money_account(ctx, method, payment.bank_account_id)
    lines: list[dict] = []
    add = _adder(lines)
    amount = Decimal(str(payment.amount))
    add(supplier, supplier_name, amount, debit=True)
    add(money, method.short_label or method.name, amount, debit=False)
    return ("CX" if method.is_cash else "BCO"), lines


# ---------- the sources: what is posted, from what, on which day ----------

@dataclass
class _Document:
    kind: str
    id: uuid.UUID
    label: str  # «FT A2026/12», «COMP2026/3 (FT A/1)», «PAG2026/4»
    day: date
    description: str


async def _describe(db: AsyncSession, kind: str, source_id: uuid.UUID):
    """(document, object) of one source document."""
    if kind == SOURCE_INVOICE:
        invoice = await db.get(Invoice, source_id)
        return _Document(kind, invoice.id, _label(invoice), invoice.business_date, KIND_LABEL[invoice.invoice_type]), invoice
    if kind == SOURCE_PURCHASE:
        invoice = await db.get(PurchaseInvoice, source_id)
        label = f"{invoice.series}/{invoice.number} ({invoice.supplier_document})"
        name = {"FT": "Fatura de compra", "FR": "Fatura-recibo de compra", "TV": "Talão de compra",
                "NC": "Nota de crédito de fornecedor"}.get(invoice.purchase_type, "Compra")
        return _Document(kind, invoice.id, label, await _purchase_date(db, invoice), name), invoice
    payment = await db.get(SupplierPayment, source_id)
    return _Document(kind, payment.id, f"{payment.series}/{payment.number}", payment.payment_date,
                     "Pagamento a fornecedor"), payment


BUILDERS = {SOURCE_INVOICE: build_invoice_entry, SOURCE_PURCHASE: build_purchase_entry,
            SOURCE_SUPPLIER_PAYMENT: build_supplier_payment_entry}


def _posted(kind: str, column):
    return exists().where(and_(JournalEntry.source_kind == kind, JournalEntry.source_id == column))


def _waiting_queries(company_id: uuid.UUID, start: date) -> dict:
    """Per kind: the ids of the documents still without their entry, oldest first."""
    return {
        SOURCE_INVOICE: select(Invoice.id).where(
            Invoice.company_id == company_id, Invoice.invoice_type.in_(POSTED_TYPES), Invoice.issuance_mode != TRAINING,
            Invoice.business_date >= start, Invoice.total != 0, ~_posted(SOURCE_INVOICE, Invoice.id),
        ).order_by(Invoice.business_date, Invoice.created_at),
        SOURCE_PURCHASE: select(PurchaseInvoice.id).where(
            PurchaseInvoice.company_id == company_id, PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA,
            PurchaseInvoice.document_date >= start, PurchaseInvoice.total != 0, ~_posted(SOURCE_PURCHASE, PurchaseInvoice.id),
        ).order_by(PurchaseInvoice.document_date, PurchaseInvoice.created_at),
        SOURCE_SUPPLIER_PAYMENT: select(SupplierPayment.id).where(
            SupplierPayment.company_id == company_id, SupplierPayment.status == SupplierPaymentStatus.REGISTADO,
            SupplierPayment.payment_date >= start, SupplierPayment.amount != 0,
            ~_posted(SOURCE_SUPPLIER_PAYMENT, SupplierPayment.id),
        ).order_by(SupplierPayment.payment_date, SupplierPayment.created_at),
    }


def _to_reverse(company_id: uuid.UUID):
    """The entries of purchases and supplier payments cancelled since, still without their estorno: (entry id, kind,
    document id, cancellation time)."""
    estorno = aliased(JournalEntry)
    reversed_ = exists().where(estorno.reversal_of_id == JournalEntry.id)
    base = select(JournalEntry.id, JournalEntry.source_kind, JournalEntry.source_id).where(
        JournalEntry.company_id == company_id, ~reversed_)
    return [
        base.add_columns(PurchaseInvoice.cancelled_at).join(PurchaseInvoice, and_(
            JournalEntry.source_kind == SOURCE_PURCHASE, PurchaseInvoice.id == JournalEntry.source_id))
        .where(PurchaseInvoice.status == PurchaseInvoiceStatus.ANULADA),
        base.add_columns(SupplierPayment.cancelled_at).join(SupplierPayment, and_(
            JournalEntry.source_kind == SOURCE_SUPPLIER_PAYMENT, SupplierPayment.id == JournalEntry.source_id))
        .where(SupplierPayment.status == SupplierPaymentStatus.ANULADO),
    ]


async def integrate_document(db: AsyncSession, company_id: uuid.UUID, ctx: _Context, kind: str, source_id: uuid.UUID) -> bool:
    """Posts the entry of one document, or keeps it in «Por integrar» with the reason. True when posted."""
    document, obj = await _describe(db, kind, source_id)
    try:
        code, lines = await BUILDERS[kind](db, ctx, obj)
        journal = ctx.journals.get(code)
        if journal is None:
            raise IntegrationError(f"O diário {code} não existe - crie-o em Lançamentos › Diários")
        party = lines[0]["description"] if kind == SOURCE_INVOICE else next(
            (l["description"] for l in lines if l["account_id"] in _party_accounts(ctx)), "")
        await save_entry(db, company_id, None, entry_id=None, journal_id=journal.id, entry_date=document.day,
                         description=f"{document.description} - {party}" if party else document.description,
                         document_ref=document.label[:60], lines=lines, post=True, source=(kind, document.id))
    except (IntegrationError, JournalError) as e:
        await _keep_pending(db, company_id, document, str(e))
        return False
    await _clear_pending(db, company_id, kind, document.id)
    return True


def _party_accounts(ctx: _Context) -> set[uuid.UUID]:
    """The accounts of customers and suppliers (to name the entry after its party)."""
    out = {a.id for (kind, _), a in ctx.links.items() if kind in ("CUSTOMER", "SUPPLIER")}
    out |= {ctx.mappings[k].id for k in ("PARENT_SUPPLIERS", "PARENT_CUSTOMERS_NATIONAL", "PARENT_CUSTOMERS_FOREIGN",
                                         "CUSTOMERS_GENERIC") if k in ctx.mappings}
    return out


async def _reverse_cancelled(db: AsyncSession, company_id: uuid.UUID, entry_id: uuid.UUID, kind: str,
                             source_id: uuid.UUID, cancelled_at) -> bool:
    """The estorno of the entry of a cancelled purchase or payment, on its cancellation day."""
    from app.services.journal_service import reverse_entry
    entry = await db.get(JournalEntry, entry_id)
    day = max(cancelled_at.astimezone(LUANDA).date() if cancelled_at else date.today(), entry.entry_date)
    document, _obj = await _describe(db, kind, source_id)
    try:
        await reverse_entry(db, company_id, None, entry_id, day)
    except JournalError as e:
        await _keep_pending(db, company_id, document, f"Anulado - o estorno do lançamento não pôde ser feito: {e}")
        return False
    await _clear_pending(db, company_id, kind, source_id)
    return True


async def _keep_pending(db: AsyncSession, company_id: uuid.UUID, document: _Document, reason: str) -> None:
    row = (await db.execute(select(PendingIntegration).where(
        PendingIntegration.company_id == company_id, PendingIntegration.source_kind == document.kind,
        PendingIntegration.source_id == document.id))).scalar_one_or_none()
    if row is None:
        db.add(PendingIntegration(company_id=company_id, source_kind=document.kind, source_id=document.id,
                                  document=document.label[:60], document_date=document.day, reason=reason[:300]))
    elif row.reason != reason[:300]:
        row.reason = reason[:300]
    await db.commit()


async def _clear_pending(db: AsyncSession, company_id: uuid.UUID, kind: str, source_id: uuid.UUID) -> None:
    await db.execute(delete(PendingIntegration).where(
        PendingIntegration.company_id == company_id, PendingIntegration.source_kind == kind,
        PendingIntegration.source_id == source_id))
    await db.commit()


async def integrate_company(db: AsyncSession, company_id: uuid.UUID, limit: int = BATCH) -> dict:
    """One round for one company: {posted, pending} - the documents' entries, then the estornos of the cancelled ones.
    Nothing before the chart is started."""
    settings = await db.get(AccountingSettings, company_id)
    if settings is None or settings.chart_source is None or settings.integration_start is None:
        return {"posted": 0, "pending": 0}
    start = settings.integration_start
    # the documents now before the start day are no longer waiting
    await db.execute(delete(PendingIntegration).where(
        PendingIntegration.company_id == company_id, PendingIntegration.document_date < start))
    await db.commit()
    work = []
    for kind, query in _waiting_queries(company_id, start).items():
        work += [("post", kind, source_id) for source_id in (await db.execute(query.limit(limit))).scalars().all()]
    for query in _to_reverse(company_id):
        work += [("reverse", kind, (entry_id, source_id, cancelled_at))
                 for entry_id, kind, source_id, cancelled_at in (await db.execute(query.limit(limit))).all()]
    if not work:
        return {"posted": 0, "pending": 0}
    from app.services.account_mapping_service import sync_subaccounts
    await sync_subaccounts(db, company_id)  # a sub-account still missing (a customer created before the chart...)
    ctx = None
    posted = pending = 0
    for action, kind, target in work:
        if ctx is None:
            ctx = await _context(db, company_id, await db.get(AccountingSettings, company_id))
        try:
            if action == "post":
                done = await integrate_document(db, company_id, ctx, kind, target)
            else:
                done = await _reverse_cancelled(db, company_id, target[0], kind, target[1], target[2])
        except Exception:  # noqa: BLE001 - one document never stops the others
            log.exception("%s %s %s not integrated", action, kind, target)
            await db.rollback()
            ctx = None  # the rollback expired what was read: read it again
            done = False
        posted, pending = posted + done, pending + (not done)
    return {"posted": posted, "pending": pending}


async def list_pending(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(select(PendingIntegration).where(PendingIntegration.company_id == company_id)
                             .order_by(PendingIntegration.document_date, PendingIntegration.document))).scalars().all()
    return [{"id": r.id, "document": r.document, "document_date": r.document_date, "reason": r.reason,
             "updated_at": r.updated_at} for r in rows]


async def set_integration_start(db: AsyncSession, company_id: uuid.UUID, start: date) -> None:
    settings = await db.get(AccountingSettings, company_id)
    if settings is None or settings.chart_source is None:
        raise IntegrationError("Comece primeiro o plano de contas")
    settings.integration_start = start
    await db.commit()


async def integration_status(db: AsyncSession, company_id: uuid.UUID) -> dict:
    settings = await db.get(AccountingSettings, company_id)
    start = settings.integration_start if settings else None
    waiting = 0
    if start is not None:
        from sqlalchemy import func
        for query in _waiting_queries(company_id, start).values():
            waiting += (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    return {"integration_start": start, "waiting": waiting, "pending": await list_pending(db, company_id)}


async def integration_loop() -> None:
    """Started with the server: every minute, the new documents of every company whose chart is started."""
    from app.core.database import AsyncSessionLocal
    while True:
        try:
            async with AsyncSessionLocal() as db:
                companies = (await db.execute(select(AccountingSettings.company_id).where(
                    AccountingSettings.chart_source.is_not(None), AccountingSettings.integration_start.is_not(None)))).scalars().all()
                for company_id in companies:
                    try:
                        await integrate_company(db, company_id)
                    except Exception:  # noqa: BLE001 - one company never stops the others
                        log.exception("integration failed for company %s", company_id)
                        await db.rollback()
        except Exception:  # noqa: BLE001 - the loop never stops on one failure
            log.exception("integration loop failed")
        await asyncio.sleep(LOOP_SECONDS)
