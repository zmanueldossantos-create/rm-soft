"""
Tesouraria - the company's bank accounts: their balance and their statement (extrato), with or without the accounting.

A bank account's movements are read from the documents that already name it - nothing is typed twice:
  - the money collected on it: the payments of a sale, a receipt or a down payment whose method lands on a bank account
    (uses_bank_account: transfer, card, Multicaixa...) and whose document names this account; a refund of a credit
    note (a negative payment) leaves it;
  - the money paid from it: the supplier payments made from this account; a cancelled one comes back on its
    cancellation day, so the statement keeps both.
The starting point is the account's opening balance: the bank statement's balance on the day the company starts
following the account here (opening_date) - the movements before that day are inside that balance and not counted.
Documents of Modo formação never move money.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from app.models.company_bank_account import CompanyBankAccount
from app.models.currency import Currency
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.supplier import Supplier
from app.models.supplier_payment import SupplierPayment, SupplierPaymentStatus
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE

LUANDA = ZoneInfo("Africa/Luanda")


class BankAccountNotFoundError(Exception):
    pass


class InvalidOpeningBalanceError(Exception):
    pass


@dataclass
class _Line:
    day: date
    at: datetime  # the order inside a day
    document: str
    description: str
    amount: float  # > 0 in, < 0 out


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
        select(Invoice, Payment.amount, PaymentMethodCatalog.name, Customer.name)
        .join(Payment, Payment.invoice_id == Invoice.id)
        .join(PaymentMethodCatalog, PaymentMethodCatalog.id == Payment.payment_method_id)
        .outerjoin(Customer, Customer.id == Invoice.customer_id)
        .where(Invoice.company_id == company_id, Invoice.bank_account_id == account.id,
               PaymentMethodCatalog.uses_bank_account.is_(True), Invoice.issuance_mode != "FORMACAO")
    )).all()
    for invoice, amount, method_name, customer_name in collected:
        code = DOC_CODE_BY_INVOICE_TYPE.get(invoice.invoice_type.value, invoice.invoice_type.value)
        refund = float(amount) < 0
        lines.append(_Line(
            day=invoice.business_date, at=invoice.created_at, document=f"{code} {invoice.series}/{invoice.number}",
            description=" · ".join(filter(None, [customer_name, method_name, "Reembolso" if refund else None])),
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
    """Each bank account of the company with its balance today."""
    out = []
    for account, acronym, full_name, currency in await _accounts(db, company_id):
        lines = await _lines(db, company_id, account)
        row = _describe(account, acronym, full_name, currency)
        row["balance"] = round(row["opening_balance"] + sum(line.amount for line in lines), 2)
        row["movements"] = len(lines)
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
            "balance": round(balance, 2),
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
