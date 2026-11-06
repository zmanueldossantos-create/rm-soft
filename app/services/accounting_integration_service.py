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
The customer: its sub-account; a final consumer or no customer: «Consumidor final»; the company keeping no
sub-account per customer: the parent account (national or foreign) itself. The till: the sub-account of the caixa of
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

from sqlalchemy import and_, delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.recipe_ingredient import RecipeIngredient
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
from app.services.journal_service import JournalError, save_entry

log = logging.getLogger(__name__)

SOURCE_INVOICE = "INVOICE"
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


async def _treasury(db: AsyncSession, ctx: _Context, invoice: Invoice, method: PaymentMethodCatalog) -> Account:
    """Where the money of one payment is: the caixa (cash) or the bank account (the methods that use one)."""
    if method.is_cash:
        pos_id = None
        if invoice.cash_session_id:
            pos_id = (await db.execute(select(CashSession.pos_id).where(CashSession.id == invoice.cash_session_id))).scalar_one_or_none()
        if pos_id is None:  # cash taken outside a cash session: the activity's default caixa
            pos_id = (await db.execute(select(PointOfSale.id).where(
                PointOfSale.activity_id == invoice.activity_id, PointOfSale.is_default.is_(True)))).scalar_one_or_none()
        account = ctx.links.get(("TILL", pos_id)) if pos_id else None
        if account is None:
            raise IntegrationError("A caixa do pagamento ainda não tem subconta - defina a conta-mãe das caixas em "
                                   "Contas por operação")
        return account
    if method.uses_bank_account:
        if invoice.bank_account_id is None:
            raise IntegrationError(f"O documento não indica a conta bancária do pagamento ({method.name})")
        account = ctx.links.get(("BANK", invoice.bank_account_id))
        if account is None:
            raise IntegrationError("A conta bancária do pagamento ainda não tem subconta - defina a conta-mãe dos "
                                   "bancos em Contas por operação")
        return account
    account = ctx.mappings.get("OTHER_MEANS")  # the other methods: the account the company chose for them
    if account is None:
        raise IntegrationError(f"O meio de pagamento «{method.name}» não leva o dinheiro a uma caixa nem a um banco - "
                               "defina a conta de «Outros meios de pagamento» em Contas por operação")
    return account


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


async def build_invoice_entry(db: AsyncSession, ctx: _Context, invoice: Invoice) -> tuple[str, list[dict]]:
    """(journal code, lines) of a sales document - IntegrationError when an account is missing."""
    customer, customer_name = await _customer(db, ctx, invoice)
    lines: list[dict] = []

    def add(account: Account, description: str, amount: Decimal, debit: bool) -> None:
        amount = amount.quantize(Decimal("0.01"))
        if amount < 0:  # a negative amount is the other side
            amount, debit = -amount, not debit
        if amount:
            lines.append({"account_id": account.id, "description": description[:200],
                          "debit": amount if debit else ZERO, "credit": ZERO if debit else amount})

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


async def integrate_invoice(db: AsyncSession, company_id: uuid.UUID, ctx: _Context, invoice: Invoice) -> bool:
    """Posts the entry of one document, or keeps it in «Por integrar» with the reason. True when posted."""
    label, invoice_id, business_date, kind = _label(invoice), invoice.id, invoice.business_date, KIND_LABEL[invoice.invoice_type]
    try:
        code, lines = await build_invoice_entry(db, ctx, invoice)
        journal = ctx.journals.get(code)
        if journal is None:
            raise IntegrationError(f"O diário {code} não existe - crie-o em Lançamentos › Diários")
        customer = next((l["description"] for l in lines), "")
        await save_entry(db, company_id, None, entry_id=None, journal_id=journal.id, entry_date=business_date,
                         description=f"{kind} - {customer}", document_ref=label, lines=lines, post=True,
                         source=(SOURCE_INVOICE, invoice_id))
    except (IntegrationError, JournalError) as e:
        await _keep_pending(db, company_id, invoice_id, label, business_date, str(e))
        return False
    await db.execute(delete(PendingIntegration).where(
        PendingIntegration.company_id == company_id, PendingIntegration.source_kind == SOURCE_INVOICE,
        PendingIntegration.source_id == invoice_id))
    await db.commit()
    return True


async def _keep_pending(db: AsyncSession, company_id: uuid.UUID, source_id: uuid.UUID, label: str, day: date, reason: str) -> None:
    row = (await db.execute(select(PendingIntegration).where(
        PendingIntegration.company_id == company_id, PendingIntegration.source_kind == SOURCE_INVOICE,
        PendingIntegration.source_id == source_id))).scalar_one_or_none()
    if row is None:
        db.add(PendingIntegration(company_id=company_id, source_kind=SOURCE_INVOICE, source_id=source_id,
                                  document=label[:60], document_date=day, reason=reason[:300]))
    elif row.reason != reason[:300]:
        row.reason = reason[:300]
    await db.commit()


def _to_post(company_id: uuid.UUID, start: date):
    """The sales documents of the company still without their entry."""
    posted = exists().where(and_(JournalEntry.company_id == company_id, JournalEntry.source_kind == SOURCE_INVOICE,
                                 JournalEntry.source_id == Invoice.id))
    return (select(Invoice).where(
        Invoice.company_id == company_id, Invoice.invoice_type.in_(POSTED_TYPES), Invoice.issuance_mode != TRAINING,
        Invoice.business_date >= start, Invoice.total != 0, ~posted,
    ).order_by(Invoice.business_date, Invoice.created_at))


async def integrate_company(db: AsyncSession, company_id: uuid.UUID, limit: int = BATCH) -> dict:
    """One round for one company: {posted, pending}. Nothing before the chart is started."""
    settings = await db.get(AccountingSettings, company_id)
    if settings is None or settings.chart_source is None or settings.integration_start is None:
        return {"posted": 0, "pending": 0}
    start = settings.integration_start
    # the documents now before the start day are no longer waiting
    await db.execute(delete(PendingIntegration).where(
        PendingIntegration.company_id == company_id, PendingIntegration.document_date < start))
    await db.commit()
    ids = (await db.execute(_to_post(company_id, start).with_only_columns(Invoice.id).limit(limit))).scalars().all()
    if not ids:
        return {"posted": 0, "pending": 0}
    from app.services.account_mapping_service import sync_subaccounts
    await sync_subaccounts(db, company_id)  # a sub-account still missing (a customer created before the chart...)
    ctx = None
    posted = pending = 0
    for invoice_id in ids:
        if ctx is None:
            ctx = await _context(db, company_id, await db.get(AccountingSettings, company_id))
        try:
            if await integrate_invoice(db, company_id, ctx, await db.get(Invoice, invoice_id)):
                posted += 1
            else:
                pending += 1
        except Exception:  # noqa: BLE001 - one document never stops the others
            log.exception("document %s not integrated", invoice_id)
            await db.rollback()
            ctx = None  # the rollback expired what was read: read it again
            pending += 1
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
        waiting = (await db.execute(select(func.count()).select_from(_to_post(company_id, start).subquery()))).scalar_one()
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
