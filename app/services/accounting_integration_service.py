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
Treasury (journal CX for the tills, BCO for the banks):
  - between two tills, once received: the receiving till debited, the sending one credited;
  - a deposit: the bank debited, the till credited; a withdrawal the other way;
  - a till's or a bank's entry or exit with a reason: the till or bank and the reason's account (set per reason in
    Contas por operação); the till side of a supplier payment is left out (posted with the payment);
  - a transfer between two banks: «em trânsito» (48) debited and the first account credited when it leaves, the second
    account debited and 48 credited when the funds are available; within one bank, straight from one to the other;
  - the difference found at a till's closing: «Falta de caixa» or «Sobra de caixa» against the till.
A purchase, a supplier payment, a bank movement or a bank transfer cancelled after its entry: the estorno of that
entry, on the cancellation day.
Stock (inventário permanente - AccountingSettings.inventory_system; nothing in the intermitente; journal OD), at the
cost of each movement:
  - a stock document (EA, SA, Oferta...): the stock of each product (goods 26, raw materials 22.1, products made 24.1)
    and the other side - the purchases (21) for the system's own documents (a purchase's goods in, a cancelled
    purchase's out), the account chosen for the document's type otherwise;
  - the other movements of one warehouse, one entry per day once the day is over: the sales and guides to customers
    to «Custo das existências vendidas» (their returns back), the internal consumption, the losses and inventory
    differences, the production (the ingredients consumed into the products made). A movement without a known cost
    is left out.

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
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.data.account_operations import OPERATIONS_BY_KEY
from app.models.account import Account, AccountingSettings, AccountLink, AccountMapping
from app.models.bank_movement import BankMovement, BankMovementStatus
from app.models.bank_transfer import BankTransfer, BankTransferStatus
from app.models.cash_movement import CashMovement, CashMovementStatus, CashMovementType
from app.models.cash_movement_reason import CashMovementReason
from app.models.cash_session import CashSession, CashSessionStatus
from app.models.company_bank_account import CompanyBankAccount
from app.models.account import StockTypeAccount
from app.models.movement_type import MovementDirection, MovementType as StockTypeCatalog
from app.models.stock_movement import MovementType as LedgerType, StockMovement
from app.models.stock_movement_document import StockMovementDocument
from app.models.warehouse import Warehouse
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
SOURCE_CASH_MOVEMENT = "CASH_MOVEMENT"
SOURCE_BANK_MOVEMENT = "BANK_MOVEMENT"
SOURCE_BANK_TRANSFER = "BANK_TRANSFER"  # its leaving the first account (or the whole transfer within one bank)
SOURCE_BANK_TRANSFER_IN = "BANK_TRANSFER_IN"  # its arrival on the second account («Fundos disponíveis»)
SOURCE_CASH_CLOSING = "CASH_CLOSING"
SOURCE_STOCK_DOCUMENT = "STOCK_DOCUMENT"  # a stock entry or exit document (EA, SA, Oferta...)
SOURCE_STOCK_DAY = "STOCK_DAY"  # the other stock movements of one warehouse on one day (the sales' cost...)
STOCK_DAY_NAMESPACE = uuid.UUID("6f1d5a52-3c1e-4e43-9d7a-5b0f6f0a2c11")
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


# ---------- treasury ----------

def _bank(ctx: _Context, bank_account_id: uuid.UUID) -> Account:
    account = ctx.links.get(("BANK", bank_account_id))
    if account is None:
        raise IntegrationError("A conta bancária ainda não tem subconta - defina a conta-mãe dos bancos em Contas por operação")
    return account


async def _reason_account(db: AsyncSession, ctx: _Context, reason_id: uuid.UUID | None) -> tuple[Account, str]:
    reason = await db.get(CashMovementReason, reason_id) if reason_id else None
    if reason is None:
        raise IntegrationError("O movimento não tem motivo")
    account = ctx.accounts.get(reason.account_id) if reason.account_id else None
    if account is None:
        raise IntegrationError(f"Defina a conta do motivo «{reason.name}» em Contas por operação › Motivos de tesouraria")
    return account, reason.name


async def build_cash_movement_entry(db: AsyncSession, ctx: _Context, movement: CashMovement) -> tuple[str, list[dict]]:
    """Between two tills: the receiving one debited, the sending one credited. A deposit: the bank debited, the till
    credited; a withdrawal the other way. An entry or exit with a reason: the till and the reason's account."""
    lines: list[dict] = []
    add = _adder(lines)
    amount = Decimal(str(movement.amount))
    kind = movement.movement_type
    if kind == CashMovementType.TRANSFERENCIA:
        add(_till(ctx, movement.destination_pos_id), "Transferência recebida", amount, debit=True)
        add(_till(ctx, movement.source_pos_id), "Transferência enviada", amount, debit=False)
    elif movement.bank_account_id is not None:
        deposit = kind == CashMovementType.SAIDA_EXTERNA
        till = _till(ctx, movement.source_pos_id if deposit else movement.destination_pos_id)
        add(_bank(ctx, movement.bank_account_id), "Depósito" if deposit else "Levantamento", amount, debit=deposit)
        add(till, "Depósito" if deposit else "Levantamento", amount, debit=not deposit)
    else:
        other, name = await _reason_account(db, ctx, movement.reason_id)
        entry = kind == CashMovementType.ENTRADA_EXTERNA
        till = _till(ctx, movement.destination_pos_id if entry else movement.source_pos_id)
        add(till, name, amount, debit=entry)
        add(other, name, amount, debit=not entry)
    return "CX", lines


async def build_bank_movement_entry(db: AsyncSession, ctx: _Context, movement: BankMovement) -> tuple[str, list[dict]]:
    """A movement typed on a bank account: the bank and its reason's account."""
    other, name = await _reason_account(db, ctx, movement.reason_id)
    lines: list[dict] = []
    add = _adder(lines)
    amount = Decimal(str(movement.amount))
    incoming = movement.direction.value == "ENTRADA"
    add(_bank(ctx, movement.bank_account_id), name, amount, debit=incoming)
    add(other, name, amount, debit=not incoming)
    return "BCO", lines


async def _same_bank(db: AsyncSession, transfer: BankTransfer) -> bool:
    banks = (await db.execute(select(CompanyBankAccount.id, CompanyBankAccount.bank_id).where(
        CompanyBankAccount.id.in_([transfer.from_account_id, transfer.to_account_id])))).all()
    return len({bank_id for _, bank_id in banks}) == 1


async def build_bank_transfer_entry(db: AsyncSession, ctx: _Context, transfer: BankTransfer) -> tuple[str, list[dict]]:
    """Leaving the first account: «em trânsito» debited, the first account credited - within one bank, straight to
    the second account."""
    lines: list[dict] = []
    add = _adder(lines)
    amount = Decimal(str(transfer.amount))
    target = _bank(ctx, transfer.to_account_id) if await _same_bank(db, transfer) else _mapped(ctx, "BANK_TRANSIT")
    add(target, "Transferência bancária", amount, debit=True)
    add(_bank(ctx, transfer.from_account_id), "Transferência bancária", amount, debit=False)
    return "BCO", lines


async def build_bank_transfer_in_entry(db: AsyncSession, ctx: _Context, transfer: BankTransfer) -> tuple[str, list[dict]]:
    """The funds available on the second account: that account debited, «em trânsito» credited."""
    lines: list[dict] = []
    add = _adder(lines)
    amount = Decimal(str(transfer.amount))
    add(_bank(ctx, transfer.to_account_id), "Fundos disponíveis", amount, debit=True)
    add(_mapped(ctx, "BANK_TRANSIT"), "Fundos disponíveis", amount, debit=False)
    return "BCO", lines


async def build_cash_closing_entry(db: AsyncSession, ctx: _Context, session: CashSession) -> tuple[str, list[dict]]:
    """The difference found at a till's closing: a shortage to «Falta de caixa», a surplus to «Sobra de caixa»."""
    lines: list[dict] = []
    add = _adder(lines)
    difference = Decimal(str(session.closing_difference))
    till = _till(ctx, session.pos_id)
    if difference < 0:
        add(_mapped(ctx, "CASH_SHORTAGE"), "Falta de caixa", -difference, debit=True)
        add(till, "Falta de caixa", -difference, debit=False)
    else:
        add(till, "Sobra de caixa", difference, debit=True)
        add(_mapped(ctx, "CASH_SURPLUS"), "Sobra de caixa", difference, debit=False)
    return "CX", lines


# ---------- stock (inventário permanente) ----------

async def _stock_accounts(db: AsyncSession, ctx: _Context, product_ids) -> dict[uuid.UUID, tuple[str, str]]:
    """Per product: (its stock operation, its purchases operation) - raw materials, products made by the company (a
    recipe), goods."""
    ids = list(set(product_ids))
    raw = set((await db.execute(select(Product.id).where(Product.id.in_(ids), Product.is_raw_material.is_(True)))).scalars().all())
    made = set((await db.execute(select(RecipeIngredient.finished_product_id).where(
        RecipeIngredient.finished_product_id.in_(ids)))).scalars().all())
    return {pid: ("STOCK_MATERIALS", "PURCHASES_MATERIALS") if pid in raw else
            ("STOCK_PRODUCTS", "PURCHASES_GOODS") if pid in made else ("STOCK_GOODS", "PURCHASES_GOODS") for pid in ids}


def _value(row: StockMovement) -> Decimal:
    return (abs(Decimal(str(row.quantity))) * Decimal(str(row.unit_cost))).quantize(Decimal("0.01"))


def _pairs_to_lines(ctx: _Context, pairs: list[tuple[str, str, str, Decimal]]) -> list[dict]:
    """[(debit operation, credit operation, label, value)] -> the lines, summed per account and side."""
    debit: dict[tuple[str, str], Decimal] = {}
    credit: dict[tuple[str, str], Decimal] = {}
    for d, c, label, value in pairs:
        debit[(d, label)] = debit.get((d, label), ZERO) + value
        credit[(c, label)] = credit.get((c, label), ZERO) + value
    lines: list[dict] = []
    add = _adder(lines)
    for (key, label), value in debit.items():
        add(ctx.accounts[key] if isinstance(key, uuid.UUID) else _mapped(ctx, key), label, value, debit=True)
    for (key, label), value in credit.items():
        add(ctx.accounts[key] if isinstance(key, uuid.UUID) else _mapped(ctx, key), label, value, debit=False)
    return lines


def _document_ref(document: StockMovementDocument) -> str:
    return f"{document.series}/{document.number}"


async def build_stock_document_entry(db: AsyncSession, ctx: _Context, document: StockMovementDocument) -> tuple[str, list[dict]]:
    """A stock document at the cost of its lines: the stock of each product and the other side - the purchases for the
    system's own entries and exits (a purchase's goods in, a cancelled purchase's out), the account chosen for its type
    otherwise. An entry debits the stock, an exit credits it."""
    kind = await db.get(StockTypeCatalog, document.movement_type_id)
    rows = (await db.execute(select(StockMovement).where(
        StockMovement.company_id == document.company_id, StockMovement.reference == _document_ref(document),
        StockMovement.warehouse_id == document.warehouse_id, StockMovement.unit_cost.is_not(None)))).scalars().all()
    entry = kind.direction == MovementDirection.ENTRADA
    other_account = None
    if not kind.is_auto:
        other_account = (await db.execute(select(StockTypeAccount.account_id).where(
            StockTypeAccount.company_id == document.company_id, StockTypeAccount.movement_type_id == kind.id))).scalar_one_or_none()
        if other_account not in ctx.accounts:
            raise IntegrationError(f"Defina a conta do tipo de movimento «{kind.name}» em Contas por operação")
    accounts = await _stock_accounts(db, ctx, [r.product_id for r in rows])
    pairs = []
    for row in rows:
        stock_op, purchases_op = accounts[row.product_id]
        other = other_account or purchases_op
        value = _value(row)
        pairs.append((stock_op, other, kind.name, value) if entry else (other, stock_op, kind.name, value))
    return "OD", _pairs_to_lines(ctx, pairs)


def _document_refs(company_id: uuid.UUID):
    """The references the stock documents write on their ledger rows («EA2026/3»)."""
    return select(func.concat(StockMovementDocument.series, "/", StockMovementDocument.number)).where(
        StockMovementDocument.company_id == company_id)


def _day_of(column):
    return func.date(func.timezone("Africa/Luanda", column))


async def build_stock_day_entry(db: AsyncSession, ctx: _Context, target: tuple) -> tuple[str, list[dict]]:
    """The stock movements of one warehouse on one day that have no document of their own, at their cost: the sales
    (and the guides to customers) to «Custo das existências vendidas», their returns back; the internal consumption;
    the losses and the inventory differences; the production (the ingredients consumed into the products made)."""
    company_id, warehouse_id, day = target
    rows = (await db.execute(select(StockMovement).where(
        StockMovement.company_id == company_id, StockMovement.warehouse_id == warehouse_id,
        _day_of(StockMovement.created_at) == day, StockMovement.movement_type != LedgerType.TRANSFERENCIA,
        StockMovement.unit_cost.is_not(None), StockMovement.unit_cost != 0,
        func.coalesce(StockMovement.reference, "").not_in(_document_refs(company_id)),
    ).order_by(StockMovement.created_at))).scalars().all()
    accounts = await _stock_accounts(db, ctx, [r.product_id for r in rows])
    pairs = []
    for row in rows:
        stock_op = accounts[row.product_id][0]
        value = _value(row)
        kind = row.movement_type
        if kind == LedgerType.SAIDA:
            if (row.reference or "").startswith("Consumo interno"):
                pairs.append(("STOCK_INTERNAL_USE", stock_op, "Consumo interno", value))
            else:
                pairs.append(("COST_OF_SALES", stock_op, "Custo das vendas", value))
        elif kind == LedgerType.RECEPCAO:  # goods back from a credit note or a cancelled guide
            pairs.append((stock_op, "COST_OF_SALES", "Devoluções", value))
        elif kind == LedgerType.PERDA:
            pairs.append(("STOCK_LOSSES", stock_op, "Quebras", value))
        elif kind == LedgerType.AJUSTE:
            if Decimal(str(row.quantity)) > 0:
                pairs.append((stock_op, "STOCK_GAINS", "Sobras", value))
            else:
                pairs.append(("STOCK_LOSSES", stock_op, "Quebras", value))
        elif kind == LedgerType.PRODUCAO and not row.is_production_output:  # the product made carries what it consumed
            pairs.append(("STOCK_PRODUCTS", stock_op, "Produção", value))
    return "OD", _pairs_to_lines(ctx, pairs)


def _today() -> date:
    """Today in Luanda: a day's stock is posted once it is over."""
    return datetime.now(LUANDA).date()


async def _stock_days(db: AsyncSession, company_id: uuid.UUID, start: date) -> list[tuple[uuid.UUID, tuple]]:
    """The (warehouse, day) still without their stock entry: the days before today with a movement at a cost."""
    today = _today()
    day = _day_of(StockMovement.created_at)
    pairs = (await db.execute(select(StockMovement.warehouse_id, day).where(
        StockMovement.company_id == company_id, day >= start, day < today,
        StockMovement.movement_type != LedgerType.TRANSFERENCIA,
        StockMovement.unit_cost.is_not(None), StockMovement.unit_cost != 0,
        func.coalesce(StockMovement.reference, "").not_in(_document_refs(company_id)),
    ).group_by(StockMovement.warehouse_id, day).order_by(day))).all()
    posted = set((await db.execute(select(JournalEntry.source_id).where(
        JournalEntry.company_id == company_id, JournalEntry.source_kind == SOURCE_STOCK_DAY))).scalars().all())
    out = []
    for warehouse_id, d in pairs:
        source_id = uuid.uuid5(STOCK_DAY_NAMESPACE, f"{company_id}:{warehouse_id}:{d.isoformat()}")
        if source_id not in posted:
            out.append((source_id, (company_id, warehouse_id, d)))
    return out


def _local_day(moment, default: date) -> date:
    return moment.astimezone(LUANDA).date() if moment else default


# ---------- the sources: what is posted, from what, on which day ----------

@dataclass
class _Document:
    kind: str
    id: uuid.UUID
    label: str  # «FT A2026/12», «COMP2026/3 (FT A/1)», «PAG2026/4»
    day: date
    description: str


async def _describe(db: AsyncSession, kind: str, source_id: uuid.UUID, extra=None):
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
    if kind == SOURCE_SUPPLIER_PAYMENT:
        payment = await db.get(SupplierPayment, source_id)
        return _Document(kind, payment.id, f"{payment.series}/{payment.number}", payment.payment_date,
                         "Pagamento a fornecedor"), payment
    if kind == SOURCE_CASH_MOVEMENT:
        movement = await db.get(CashMovement, source_id)
        name = {CashMovementType.TRANSFERENCIA: "Transferência entre caixas"}.get(movement.movement_type)
        if name is None and movement.bank_account_id:
            name = "Depósito no banco" if movement.movement_type == CashMovementType.SAIDA_EXTERNA else "Levantamento do banco"
        if name is None:
            reason = await db.get(CashMovementReason, movement.reason_id) if movement.reason_id else None
            name = ("Entrada de caixa" if movement.movement_type == CashMovementType.ENTRADA_EXTERNA else "Saída de caixa") + \
                (f" - {reason.name}" if reason else "")
        day = _local_day(movement.received_at, movement.movement_date) \
            if movement.movement_type == CashMovementType.TRANSFERENCIA else movement.movement_date
        return _Document(kind, movement.id, f"{name} {day.strftime('%d/%m')}"[:60], day, name), movement
    if kind == SOURCE_BANK_MOVEMENT:
        movement = await db.get(BankMovement, source_id)
        name = "Entrada no banco" if movement.direction.value == "ENTRADA" else "Saída do banco"
        return _Document(kind, movement.id, f"{movement.series}/{movement.number}", movement.movement_date, name), movement
    if kind in (SOURCE_BANK_TRANSFER, SOURCE_BANK_TRANSFER_IN):
        transfer = await db.get(BankTransfer, source_id)
        label = f"{transfer.series}/{transfer.number}"
        if kind == SOURCE_BANK_TRANSFER_IN:
            return _Document(kind, transfer.id, label + " (chegada)", transfer.available_date or transfer.transfer_date,
                             "Transferência bancária - fundos disponíveis"), transfer
        return _Document(kind, transfer.id, label, transfer.transfer_date, "Transferência bancária"), transfer
    if kind == SOURCE_STOCK_DOCUMENT:
        document = await db.get(StockMovementDocument, source_id)
        type_name = (await db.execute(select(StockTypeCatalog.name).where(StockTypeCatalog.id == document.movement_type_id))).scalar_one()
        day = document.movement_date
        if document.fiscal_period_id:  # booked in another month (a late one): the first day of that period
            month, year = (await db.execute(select(FiscalPeriod.month, FiscalYear.year).join(
                FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(FiscalPeriod.id == document.fiscal_period_id))).one()
            day = day if (day.year, day.month) == (year, month) else date(year, month, 1)
        return _Document(kind, document.id, _document_ref(document), day, type_name), document
    if kind == SOURCE_STOCK_DAY:
        company_id, warehouse_id, day = extra
        name = (await db.execute(select(Warehouse.name).where(Warehouse.id == warehouse_id))).scalar_one()
        return _Document(kind, source_id, f"Stock {day.strftime('%d/%m')} - {name}"[:60], day,
                         f"Movimentos de stock do dia - {name}"), extra
    session = await db.get(CashSession, source_id)
    pos_name = (await db.execute(select(PointOfSale.name).where(PointOfSale.id == session.pos_id))).scalar_one()
    day = _local_day(session.closed_at, session.business_date)
    return _Document(kind, session.id, f"Fecho {pos_name} {session.business_date.strftime('%d/%m')}"[:60], day,
                     f"Diferença no fecho de caixa - {pos_name}"), session


BUILDERS = {SOURCE_INVOICE: build_invoice_entry, SOURCE_PURCHASE: build_purchase_entry,
            SOURCE_SUPPLIER_PAYMENT: build_supplier_payment_entry, SOURCE_CASH_MOVEMENT: build_cash_movement_entry,
            SOURCE_BANK_MOVEMENT: build_bank_movement_entry, SOURCE_BANK_TRANSFER: build_bank_transfer_entry,
            SOURCE_BANK_TRANSFER_IN: build_bank_transfer_in_entry, SOURCE_CASH_CLOSING: build_cash_closing_entry,
            SOURCE_STOCK_DOCUMENT: build_stock_document_entry, SOURCE_STOCK_DAY: build_stock_day_entry}


def _posted(kind: str, column):
    return exists().where(and_(JournalEntry.source_kind == kind, JournalEntry.source_id == column))


def _waiting_queries(company_id: uuid.UUID, start: date, permanent: bool = True) -> dict:
    """Per kind: the ids of the documents still without their entry, oldest first (the stock ones in the inventário
    permanente only; the stock days: _stock_days)."""
    from_account, to_account = aliased(CompanyBankAccount), aliased(CompanyBankAccount)
    stock = {SOURCE_STOCK_DOCUMENT: select(StockMovementDocument.id).where(
        StockMovementDocument.company_id == company_id, StockMovementDocument.movement_date >= start,
        ~_posted(SOURCE_STOCK_DOCUMENT, StockMovementDocument.id),
        exists().where(and_(StockMovement.company_id == company_id,  # at least one line at a cost
                            StockMovement.reference == func.concat(StockMovementDocument.series, "/", StockMovementDocument.number),
                            StockMovement.unit_cost.is_not(None), StockMovement.unit_cost != 0)),
    ).order_by(StockMovementDocument.movement_date, StockMovementDocument.created_at)} if permanent else {}
    return {**stock,
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
        SOURCE_CASH_MOVEMENT: select(CashMovement.id).where(
            CashMovement.company_id == company_id, CashMovement.status == CashMovementStatus.RECEBIDO,
            CashMovement.movement_date >= start, CashMovement.amount != 0, ~_posted(SOURCE_CASH_MOVEMENT, CashMovement.id),
            # the till's side of a supplier payment (and of its cancellation): posted with the payment
            ~exists().where(SupplierPayment.cash_movement_id == CashMovement.id),
            ~exists().where(SupplierPayment.reversal_movement_id == CashMovement.id),
        ).order_by(CashMovement.movement_date, CashMovement.created_at),
        SOURCE_BANK_MOVEMENT: select(BankMovement.id).where(
            BankMovement.company_id == company_id, BankMovement.status == BankMovementStatus.REGISTADO,
            BankMovement.movement_date >= start, ~_posted(SOURCE_BANK_MOVEMENT, BankMovement.id),
        ).order_by(BankMovement.movement_date, BankMovement.created_at),
        SOURCE_BANK_TRANSFER: select(BankTransfer.id).where(
            BankTransfer.company_id == company_id, BankTransfer.status != BankTransferStatus.ANULADO,
            BankTransfer.transfer_date >= start, ~_posted(SOURCE_BANK_TRANSFER, BankTransfer.id),
        ).order_by(BankTransfer.transfer_date, BankTransfer.created_at),
        SOURCE_BANK_TRANSFER_IN: select(BankTransfer.id)
        .join(from_account, from_account.id == BankTransfer.from_account_id)
        .join(to_account, to_account.id == BankTransfer.to_account_id).where(
            BankTransfer.company_id == company_id, BankTransfer.status == BankTransferStatus.DISPONIVEL,
            from_account.bank_id != to_account.bank_id,  # within one bank: no arrival of its own
            BankTransfer.transfer_date >= start, _posted(SOURCE_BANK_TRANSFER, BankTransfer.id),  # after its leaving
            ~_posted(SOURCE_BANK_TRANSFER_IN, BankTransfer.id),
        ).order_by(BankTransfer.available_date, BankTransfer.created_at),
        SOURCE_CASH_CLOSING: select(CashSession.id).where(
            CashSession.company_id == company_id, CashSession.status == CashSessionStatus.FECHADA,
            CashSession.business_date >= start, CashSession.closing_difference.is_not(None),
            CashSession.closing_difference != 0, ~_posted(SOURCE_CASH_CLOSING, CashSession.id),
        ).order_by(CashSession.business_date, CashSession.closed_at),
    }


def _to_reverse(company_id: uuid.UUID):
    """The entries of the documents cancelled since (purchases, supplier payments, bank movements and transfers), still
    without their estorno: (entry id, kind, document id, cancellation time)."""
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
        base.add_columns(BankMovement.cancelled_at).join(BankMovement, and_(
            JournalEntry.source_kind == SOURCE_BANK_MOVEMENT, BankMovement.id == JournalEntry.source_id))
        .where(BankMovement.status == BankMovementStatus.ANULADO),
        base.add_columns(BankTransfer.cancelled_at).join(BankTransfer, and_(
            JournalEntry.source_kind.in_([SOURCE_BANK_TRANSFER, SOURCE_BANK_TRANSFER_IN]),
            BankTransfer.id == JournalEntry.source_id))
        .where(BankTransfer.status == BankTransferStatus.ANULADO),
    ]


async def integrate_document(db: AsyncSession, company_id: uuid.UUID, ctx: _Context, kind: str, source_id: uuid.UUID,
                             extra=None) -> bool:
    """Posts the entry of one document, or keeps it in «Por integrar» with the reason. True when posted."""
    document, obj = await _describe(db, kind, source_id, extra)
    try:
        code, lines = await BUILDERS[kind](db, ctx, obj)
        journal = ctx.journals.get(code)
        if journal is None:
            raise IntegrationError(f"O diário {code} não existe - crie-o em Lançamentos › Diários")
        if not lines:
            raise IntegrationError("Nada a lançar: sem valor")
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
    """The estorno of the entry of a cancelled document, on its cancellation day."""
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
    state = {"ctx": None, "synced": False, "posted": 0, "pending": 0}

    async def run(action: str, kind: str, target) -> None:
        if not state["synced"]:  # a sub-account still missing (a customer created before the chart...)
            from app.services.account_mapping_service import sync_subaccounts
            await sync_subaccounts(db, company_id)
            state["synced"] = True
        if state["ctx"] is None:
            state["ctx"] = await _context(db, company_id, await db.get(AccountingSettings, company_id))
        try:
            if action == "post":
                done = await integrate_document(db, company_id, state["ctx"], kind, target)
            elif action == "day":
                done = await integrate_document(db, company_id, state["ctx"], kind, target[0], target[1])
            else:
                done = await _reverse_cancelled(db, company_id, target[0], kind, target[1], target[2])
        except Exception:  # noqa: BLE001 - one document never stops the others
            log.exception("%s %s %s not integrated", action, kind, target)
            await db.rollback()
            state["ctx"] = None  # the rollback expired what was read: read it again
            done = False
        state["posted" if done else "pending"] += 1

    # kind after kind, each query run once the previous kinds are posted (a transfer's arrival after its leaving)
    permanent = settings.inventory_system == "PERMANENTE"
    for kind, query in _waiting_queries(company_id, start, permanent).items():
        for source_id in (await db.execute(query.limit(limit))).scalars().all():
            await run("post", kind, source_id)
    if permanent:
        for source_id, target in (await _stock_days(db, company_id, start))[:limit]:
            await run("day", SOURCE_STOCK_DAY, (source_id, target))
    for query in _to_reverse(company_id):
        for entry_id, kind, source_id, cancelled_at in (await db.execute(query.limit(limit))).all():
            await run("reverse", kind, (entry_id, source_id, cancelled_at))
    return {"posted": state["posted"], "pending": state["pending"]}


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
        permanent = settings.inventory_system == "PERMANENTE"
        for query in _waiting_queries(company_id, start, permanent).values():
            waiting += (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        if permanent:
            waiting += len(await _stock_days(db, company_id, start))
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
