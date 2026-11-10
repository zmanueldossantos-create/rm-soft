"""
Tesouraria - the company's bank accounts: their balance and their statement (extrato), with or without the accounting.

A bank account's movements are read from the documents that already name it - nothing is typed twice:
  - the money collected on it: the payments of a sale, a receipt or a down payment whose method lands on a bank account
    (uses_bank_account: transfer, card, Multicaixa...) and whose document names this account - at the till, the
    account of the TPA / Express the payment went through (PaymentTerminal); a refund of a credit note (a negative
    payment) leaves it;
  - the money paid from it: the supplier payments made from this account; a cancelled one comes back on its
    cancellation day, so the statement keeps both;
  - the movements typed on the account in the Tesouraria (BankMovement: bank fees, a capital entry...), each with a
    reason of the catalog used for the banks; cancelled the same way;
  - the transfers between the company's accounts (BankTransfer): out on their date, in on the day the funds are
    available (the same day within one bank) - see app.services.bank_transfer_service;
  - the cash of a till deposited on the account, and the cash withdrawn into a till or the cofre (CashMovement with
    this bank account).
The starting point is the account's opening balance: the bank statement's balance on the day the company starts
following the account here (opening_date) - the movements before that day are inside that balance and not counted.
Documents of Modo formação never move money.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_movement import BankMovement, BankMovementStatus
from app.models.cash_movement_reason import CashMovementReason
from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.movement_type import MovementDirection
from app.models.user import User

from app.models.bank import Bank
from app.models.company_bank_account import CompanyBankAccount
from app.models.currency import Currency
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.payment_terminal import PaymentTerminal
from app.models.supplier import Supplier
from app.models.supplier_payment import SupplierPayment, SupplierPaymentStatus
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE

LUANDA = ZoneInfo("Africa/Luanda")


class BankAccountNotFoundError(Exception):
    pass


class InvalidOpeningBalanceError(Exception):
    pass


class BankMovementError(Exception):
    """A typed bank movement refused (its reason, amount, date or period) - 422."""


class BankMovementNotFoundError(Exception):
    pass


@dataclass
class _Line:
    day: date
    at: datetime  # the order inside a day
    document: str
    description: str
    amount: float  # > 0 in, < 0 out
    movement_id: uuid.UUID | None = None  # a typed movement still registered: it may be cancelled
    transfer_id: uuid.UUID | None = None  # a transfer not cancelled: it may be cancelled
    in_transit: bool = False  # a transfer that left this account and is not yet on the other one


async def _account_or_raise(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID) -> CompanyBankAccount:
    account = (await db.execute(select(CompanyBankAccount).where(
        CompanyBankAccount.id == account_id, CompanyBankAccount.company_id == company_id,
    ))).scalar_one_or_none()
    if account is None:
        raise BankAccountNotFoundError("Conta bancária não encontrada")
    return account


async def _lines(db: AsyncSession, company_id: uuid.UUID, account: CompanyBankAccount) -> list[_Line]:
    """Every movement of the account from its opening day, oldest first."""
    lines: list[_Line] = []

    collected = (await db.execute(
        select(Invoice, Payment.amount, PaymentMethodCatalog.name, Customer.name, PaymentTerminal.name)
        .join(Payment, Payment.invoice_id == Invoice.id)
        .join(PaymentMethodCatalog, PaymentMethodCatalog.id == Payment.payment_method_id)
        .outerjoin(Customer, Customer.id == Invoice.customer_id)
        .outerjoin(PaymentTerminal, PaymentTerminal.id == Invoice.terminal_id)
        .where(Invoice.company_id == company_id, Invoice.bank_account_id == account.id,
               PaymentMethodCatalog.uses_bank_account.is_(True), Invoice.issuance_mode != "FORMACAO")
    )).all()
    for invoice, amount, method_name, customer_name, terminal_name in collected:
        code = DOC_CODE_BY_INVOICE_TYPE.get(invoice.invoice_type.value, invoice.invoice_type.value)
        refund = float(amount) < 0
        lines.append(_Line(
            day=invoice.business_date, at=invoice.created_at, document=f"{code} {invoice.series}/{invoice.number}",
            description=" · ".join(filter(None, [customer_name, method_name, terminal_name, "Reembolso" if refund else None])),
            amount=float(amount),
        ))

    paid = (await db.execute(
        select(SupplierPayment, PaymentMethodCatalog.name, Supplier.name)
        .join(PaymentMethodCatalog, PaymentMethodCatalog.id == SupplierPayment.payment_method_id)
        .join(Supplier, Supplier.id == SupplierPayment.supplier_id)
        .where(SupplierPayment.company_id == company_id, SupplierPayment.bank_account_id == account.id)
    )).all()
    for payment, method_name, supplier_name in paid:
        document = f"{payment.series}/{payment.number}"
        lines.append(_Line(
            day=payment.payment_date, at=payment.created_at, document=document,
            description=" · ".join(filter(None, [supplier_name, method_name, payment.reference])),
            amount=-float(payment.amount),
        ))
        if payment.status == SupplierPaymentStatus.ANULADO and payment.cancelled_at is not None:
            lines.append(_Line(
                day=payment.cancelled_at.astimezone(LUANDA).date(), at=payment.cancelled_at, document=document,
                description=" · ".join(filter(None, [supplier_name, "Anulação", payment.cancel_reason])),
                amount=float(payment.amount),
            ))

    typed = (await db.execute(
        select(BankMovement, CashMovementReason.name)
        .join(CashMovementReason, CashMovementReason.id == BankMovement.reason_id)
        .where(BankMovement.company_id == company_id, BankMovement.bank_account_id == account.id)
    )).all()
    for movement, reason_name in typed:
        document = f"{movement.series}/{movement.number}"
        sign = 1 if movement.direction == MovementDirection.ENTRADA else -1
        lines.append(_Line(
            day=movement.movement_date, at=movement.created_at, document=document,
            description=" · ".join(filter(None, [reason_name, movement.description, movement.reference])),
            amount=sign * float(movement.amount),
            movement_id=movement.id if movement.status == BankMovementStatus.REGISTADO else None,
        ))
        if movement.status == BankMovementStatus.ANULADO and movement.cancelled_at is not None:
            lines.append(_Line(
                day=movement.cancelled_at.astimezone(LUANDA).date(), at=movement.cancelled_at, document=document,
                description=" · ".join(filter(None, [reason_name, "Anulação", movement.cancel_reason])),
                amount=-sign * float(movement.amount),
            ))

    from app.services.bank_transfer_service import transfer_lines  # the transfers between the company's accounts
    lines.extend(await transfer_lines(db, company_id, account))

    # the deposits of a till's cash, and the withdrawals into a till (or the cofre) - CashMovement with this account
    from app.models.cash_movement import CashMovement, CashMovementType
    from app.models.activity import Activity
    from app.models.point_of_sale import PointOfSale
    till = (await db.execute(
        select(CashMovement, PointOfSale.name, Activity.name)
        .join(PointOfSale, PointOfSale.id == func.coalesce(CashMovement.source_pos_id, CashMovement.destination_pos_id))
        .join(Activity, Activity.id == PointOfSale.activity_id)
        .where(CashMovement.company_id == company_id, CashMovement.bank_account_id == account.id)
    )).all()
    for movement, pos_name, activity_name in till:
        deposit = movement.movement_type == CashMovementType.SAIDA_EXTERNA
        lines.append(_Line(
            day=movement.movement_date, at=movement.created_at, document="Depósito" if deposit else "Levantamento",
            description=" · ".join(filter(None, [("De " if deposit else "Para ") + f"{pos_name} ({activity_name})",
                                                 movement.description])),
            amount=float(movement.amount) if deposit else -float(movement.amount),
        ))

    if account.opening_date is not None:
        lines = [line for line in lines if line.day >= account.opening_date]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    lines.sort(key=lambda line: (line.day, line.at or epoch))
    return lines


async def _accounts(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID | None = None):
    query = (select(CompanyBankAccount, Bank.acronym, Bank.full_name, Currency.code)
             .join(Bank, Bank.id == CompanyBankAccount.bank_id)
             .join(Currency, Currency.id == CompanyBankAccount.currency_id)
             .where(CompanyBankAccount.company_id == company_id))
    if account_id is not None:
        query = query.where(CompanyBankAccount.id == account_id)
    return (await db.execute(query.order_by(Bank.acronym, CompanyBankAccount.account_number))).all()


def _describe(account: CompanyBankAccount, acronym: str, full_name: str, currency: str) -> dict:
    return {
        "id": account.id, "bank": acronym, "bank_name": full_name, "account_number": account.account_number,
        "iban": account.iban, "currency": currency, "is_active": account.is_active,
        "opening_balance": float(account.opening_balance or 0), "opening_date": account.opening_date,
    }


async def list_bank_positions(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Each bank account of the company with its balance today, and the money on its way to it (em trânsito)."""
    from app.services.bank_transfer_service import in_transit_by_account
    from app.services.opening_balances_service import bank_openings
    in_transit = await in_transit_by_account(db, company_id)
    from_accounting = await bank_openings(db, company_id)  # the opening balances imported in the accounting
    out = []
    for account, acronym, full_name, currency in await _accounts(db, company_id):
        lines = await _lines(db, company_id, account)
        row = _describe(account, acronym, full_name, currency)
        imported = from_accounting.get(account.id)
        row["opening_from_accounting"] = bool(imported and float(imported[0]) == row["opening_balance"]
                                              and imported[1] == account.opening_date)
        row["balance"] = round(row["opening_balance"] + sum(line.amount for line in lines), 2)
        row["movements"] = len(lines)
        row["in_transit_in"] = in_transit.get(account.id, 0.0)
        out.append(row)
    return out


async def get_bank_statement(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID,
    date_from: date | None = None, date_to: date | None = None,
) -> dict:
    """The statement of one account over a period: the balance before it, each movement with the running balance,
    the totals and the balance at its end."""
    rows = await _accounts(db, company_id, account_id)
    if not rows:
        raise BankAccountNotFoundError("Conta bancária não encontrada")
    account, acronym, full_name, currency = rows[0]
    lines = await _lines(db, company_id, account)
    balance = float(account.opening_balance or 0)
    before = [line for line in lines if date_from is not None and line.day < date_from]
    balance += sum(line.amount for line in before)
    opening = round(balance, 2)
    entries = []
    for line in lines:
        if (date_from is not None and line.day < date_from) or (date_to is not None and line.day > date_to):
            continue
        balance += line.amount
        entries.append({
            "date": line.day, "document": line.document, "description": line.description,
            "amount_in": round(line.amount, 2) if line.amount > 0 else 0.0,
            "amount_out": round(-line.amount, 2) if line.amount < 0 else 0.0,
            "balance": round(balance, 2), "movement_id": line.movement_id,
            "transfer_id": line.transfer_id, "in_transit": line.in_transit,
        })
    return {
        "account": _describe(account, acronym, full_name, currency),
        "opening": opening,
        "total_in": round(sum(e["amount_in"] for e in entries), 2),
        "total_out": round(sum(e["amount_out"] for e in entries), 2),
        "closing": round(balance, 2),
        "lines": entries,
    }


async def set_opening_balance(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, amount: float, opening_date: date,
) -> CompanyBankAccount:
    """The bank statement's balance on the day the company starts following the account here."""
    account = await _account_or_raise(db, company_id, account_id)
    if opening_date > date.today():
        raise InvalidOpeningBalanceError("A data do saldo inicial não pode ser futura")
    account.opening_balance = round(float(amount), 2)
    account.opening_date = opening_date
    await db.commit()
    await db.refresh(account)
    return account


async def _check_date_open(db: AsyncSession, company_id: uuid.UUID, movement_date: date) -> None:
    """A typed bank movement is an internal entry: its date falls in the active period or in the soft-closed one."""
    status = (await db.execute(
        select(FiscalPeriod.status).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(
            FiscalPeriod.company_id == company_id, FiscalYear.year == movement_date.year,
            FiscalPeriod.month == movement_date.month,
        )
    )).scalar_one_or_none()
    value = status.value if hasattr(status, "value") else status
    if value not in ("ABERTO", "FECHO_PARCIAL"):
        raise BankMovementError(f"O período de {movement_date.strftime('%m/%Y')} não está aberto - escolha uma data do "
                                "período ativo ou do período em fecho parcial")


async def create_bank_movement(
    db: AsyncSession, company_id: uuid.UUID, user: User, account_id: uuid.UUID, reason_id: uuid.UUID, amount: float,
    movement_date: date, reference: str | None = None, description: str | None = None,
) -> BankMovement:
    """A movement typed on a bank account: its reason (one used for the banks) says entrada or saída. The account may
    go below zero - the screen warns, the bank decides."""
    account = await _account_or_raise(db, company_id, account_id)
    if not account.is_active:
        raise BankMovementError("Esta conta bancária está inativa")
    reason = (await db.execute(select(CashMovementReason).where(
        CashMovementReason.id == reason_id, CashMovementReason.company_id == company_id))).scalar_one_or_none()
    if reason is None or not reason.is_active or not reason.for_bank:
        raise BankMovementError("Escolha um motivo ativo dos movimentos bancários")
    amount = round(float(amount), 2)
    if amount <= 0:
        raise BankMovementError("O valor tem de ser maior que zero")
    if movement_date > date.today():
        raise BankMovementError("A data não pode ser futura")
    if account.opening_date is not None and movement_date < account.opening_date:
        raise BankMovementError(f"A data é anterior ao saldo inicial da conta ({account.opening_date.strftime('%d/%m/%Y')}) "
                                "- esse movimento já está no saldo inicial")
    await _check_date_open(db, company_id, movement_date)
    series = f"BCO{movement_date.year}"
    # one numbering at a time per company and year: two movements typed at once never get the same number
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"bankmov:{company_id}:{series}"})
    last = (await db.execute(select(func.max(BankMovement.number)).where(
        BankMovement.company_id == company_id, BankMovement.series == series))).scalar_one()
    movement = BankMovement(
        company_id=company_id, bank_account_id=account.id, reason_id=reason.id, direction=reason.direction,
        series=series, number=(last or 0) + 1, movement_date=movement_date, amount=amount,
        reference=(reference or "").strip() or None, description=(description or "").strip() or None,
        status=BankMovementStatus.REGISTADO, created_by_user_id=user.id,
    )
    db.add(movement)
    await db.commit()
    await db.refresh(movement)
    return movement


async def cancel_bank_movement(
    db: AsyncSession, company_id: uuid.UUID, movement_id: uuid.UUID, user: User, reason: str,
) -> BankMovement:
    """Cancels a typed movement - never deleted: the statement keeps it and its cancellation (today)."""
    movement = (await db.execute(select(BankMovement).where(
        BankMovement.id == movement_id, BankMovement.company_id == company_id).with_for_update())).scalar_one_or_none()
    if movement is None:
        raise BankMovementNotFoundError("Movimento bancário não encontrado")
    if movement.status == BankMovementStatus.ANULADO:
        raise BankMovementError("Este movimento já está anulado")
    reason = (reason or "").strip()
    if not reason:
        raise BankMovementError("Indique o motivo da anulação")
    await _check_date_open(db, company_id, datetime.now(LUANDA).date())
    movement.status = BankMovementStatus.ANULADO
    movement.cancel_reason = reason[:300]
    movement.cancelled_at = datetime.now(timezone.utc)
    movement.cancelled_by_user_id = user.id
    await db.commit()
    await db.refresh(movement)
    return movement
