"""
Tesouraria - the payment terminals (TPA, Multicaixa Express) and the choice of the terminal of a till payment.

A payment by card or by Express at the till lands on the bank account of the terminal it went through
(see app.models.payment_terminal). resolve_terminal picks that terminal for a sale:
  - only the payments whose method lands on a bank account count (cash and the others: no terminal);
  - the terminals that fit: active, at this point of sale (or at any point of sale), receiving every bank method of
    the payments - a document has one bank account, so its bank payments go through one terminal;
  - the one the cashier chose wins (it must fit); otherwise, when only one fits, it is taken without asking;
    when several fit, the cashier must choose; when none fits, the sale goes on without a bank (as before terminals).
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from app.models.company_bank_account import CompanyBankAccount
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.payment_terminal import PaymentTerminal, TerminalKind
from app.models.point_of_sale import PointOfSale
from app.services.invoice_service import PaymentAmountMismatchError


class PaymentTerminalError(Exception):
    """A terminal refused when it is created or changed (its name, bank account, point of sale or methods) - 422."""


class PaymentTerminalNotFoundError(Exception):
    pass


class TerminalChoiceError(PaymentAmountMismatchError):
    """The terminal of a till payment cannot be decided (to choose, or the one chosen does not fit). A payment error:
    every till route already answers PaymentAmountMismatchError with a 422 and its message."""


async def _get_or_raise(db: AsyncSession, company_id: uuid.UUID, terminal_id: uuid.UUID) -> PaymentTerminal:
    terminal = (await db.execute(select(PaymentTerminal).where(
        PaymentTerminal.id == terminal_id, PaymentTerminal.company_id == company_id,
    ))).scalar_one_or_none()
    if terminal is None:
        raise PaymentTerminalNotFoundError("Terminal não encontrado")
    return terminal


async def _describe(db: AsyncSession, terminals: list[PaymentTerminal]) -> list[dict]:
    """Each terminal with the names the screens show: its bank account and its point of sale."""
    account_ids = {t.bank_account_id for t in terminals}
    pos_ids = {t.pos_id for t in terminals if t.pos_id is not None}
    accounts = {row[0]: f"{row[1]} · {row[2]}" for row in (await db.execute(
        select(CompanyBankAccount.id, Bank.acronym, CompanyBankAccount.account_number)
        .join(Bank, Bank.id == CompanyBankAccount.bank_id).where(CompanyBankAccount.id.in_(account_ids))
    )).all()} if account_ids else {}
    pos_names = {row[0]: row[1] for row in (await db.execute(
        select(PointOfSale.id, PointOfSale.name).where(PointOfSale.id.in_(pos_ids))
    )).all()} if pos_ids else {}
    return [{
        "id": t.id, "name": t.name, "kind": t.kind.value, "bank_account_id": t.bank_account_id,
        "bank_account_label": accounts.get(t.bank_account_id, ""), "pos_id": t.pos_id,
        "pos_name": pos_names.get(t.pos_id) if t.pos_id else None,
        "payment_method_ids": list(t.payment_method_ids or []), "is_active": t.is_active,
    } for t in terminals]


async def list_terminals(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Every terminal of the company (Tesouraria › Bancos)."""
    terminals = (await db.execute(
        select(PaymentTerminal).where(PaymentTerminal.company_id == company_id).order_by(PaymentTerminal.name)
    )).scalars().all()
    return await _describe(db, list(terminals))


async def _fitting(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> list[PaymentTerminal]:
    """The active terminals usable at this point of sale (its own and the ones of any point of sale)."""
    return list((await db.execute(
        select(PaymentTerminal).where(
            PaymentTerminal.company_id == company_id, PaymentTerminal.is_active.is_(True),
            (PaymentTerminal.pos_id.is_(None)) | (PaymentTerminal.pos_id == pos_id),
        ).order_by(PaymentTerminal.name)
    )).scalars().all())


async def list_pos_terminals(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> list[dict]:
    """The terminals the till of this point of sale may use - for the cashier's choice."""
    return await _describe(db, await _fitting(db, company_id, pos_id))


async def _validated(
    db: AsyncSession, company_id: uuid.UUID, name: str, kind: str, bank_account_id: uuid.UUID,
    pos_id: uuid.UUID | None, payment_method_ids: list[uuid.UUID], terminal_id: uuid.UUID | None = None,
) -> tuple[str, TerminalKind, list[uuid.UUID]]:
    clean = (name or "").strip()
    if not clean:
        raise PaymentTerminalError("Indique o nome do terminal")
    try:
        kind_value = TerminalKind(kind)
    except ValueError:
        raise PaymentTerminalError("Tipo de terminal inválido (TPA ou Express)")
    same_name = (await db.execute(select(PaymentTerminal.id).where(
        PaymentTerminal.company_id == company_id, func.lower(PaymentTerminal.name) == clean.lower(),
    ))).scalars().all()
    if any(found != terminal_id for found in same_name):
        raise PaymentTerminalError(f"Já existe um terminal com o nome «{clean}»")
    account = (await db.execute(select(CompanyBankAccount).where(
        CompanyBankAccount.id == bank_account_id, CompanyBankAccount.company_id == company_id,
    ))).scalar_one_or_none()
    if account is None or not account.is_active:
        raise PaymentTerminalError("Conta bancária não encontrada ou inativa")
    if pos_id is not None:
        pos = (await db.execute(select(PointOfSale.id).where(
            PointOfSale.id == pos_id, PointOfSale.company_id == company_id,
        ))).scalar_one_or_none()
        if pos is None:
            raise PaymentTerminalError("Ponto de venda não encontrado")
    methods = list(dict.fromkeys(payment_method_ids or []))
    if not methods:
        raise PaymentTerminalError("Escolha pelo menos uma forma de pagamento recebida pelo terminal")
    bank_methods = set((await db.execute(select(PaymentMethodCatalog.id).where(
        PaymentMethodCatalog.id.in_(methods), PaymentMethodCatalog.uses_bank_account.is_(True),
    ))).scalars().all())
    if len(bank_methods) != len(methods):
        raise PaymentTerminalError("Um terminal só recebe formas de pagamento que entram numa conta bancária")
    return clean, kind_value, methods


async def create_terminal(
    db: AsyncSession, company_id: uuid.UUID, name: str, kind: str, bank_account_id: uuid.UUID,
    pos_id: uuid.UUID | None, payment_method_ids: list[uuid.UUID],
) -> dict:
    clean, kind_value, methods = await _validated(db, company_id, name, kind, bank_account_id, pos_id, payment_method_ids)
    terminal = PaymentTerminal(
        company_id=company_id, name=clean, kind=kind_value, bank_account_id=bank_account_id, pos_id=pos_id,
        payment_method_ids=methods, is_active=True,
    )
    db.add(terminal)
    await db.commit()
    await db.refresh(terminal)
    return (await _describe(db, [terminal]))[0]


async def update_terminal(
    db: AsyncSession, company_id: uuid.UUID, terminal_id: uuid.UUID, name: str, kind: str,
    bank_account_id: uuid.UUID, pos_id: uuid.UUID | None, payment_method_ids: list[uuid.UUID],
) -> dict:
    """A change applies to the next payments; the documents already paid keep their bank account."""
    terminal = await _get_or_raise(db, company_id, terminal_id)
    clean, kind_value, methods = await _validated(
        db, company_id, name, kind, bank_account_id, pos_id, payment_method_ids, terminal_id=terminal.id,
    )
    terminal.name, terminal.kind, terminal.bank_account_id = clean, kind_value, bank_account_id
    terminal.pos_id, terminal.payment_method_ids = pos_id, methods
    await db.commit()
    await db.refresh(terminal)
    return (await _describe(db, [terminal]))[0]


async def toggle_terminal(db: AsyncSession, company_id: uuid.UUID, terminal_id: uuid.UUID) -> dict:
    terminal = await _get_or_raise(db, company_id, terminal_id)
    terminal.is_active = not terminal.is_active
    await db.commit()
    await db.refresh(terminal)
    return (await _describe(db, [terminal]))[0]


async def resolve_terminal(
    db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID, payments: list[dict] | None,
    terminal_id: uuid.UUID | None = None,
) -> PaymentTerminal | None:
    """The terminal the bank payments of a till sale went through - see the module docstring. None: no bank payment,
    or no terminal receives them."""
    method_ids = {p["payment_method_id"] for p in (payments or []) if float(p.get("amount") or 0) > 0}
    if not method_ids:
        return None
    bank_methods = set((await db.execute(select(PaymentMethodCatalog.id).where(
        PaymentMethodCatalog.id.in_(method_ids), PaymentMethodCatalog.uses_bank_account.is_(True),
    ))).scalars().all())
    if not bank_methods:
        return None
    usable = await _fitting(db, company_id, pos_id)
    fits = [t for t in usable if bank_methods <= set(t.payment_method_ids or [])]
    if terminal_id is not None:
        chosen = next((t for t in fits if t.id == terminal_id), None)
        if chosen is None:
            raise TerminalChoiceError("O terminal escolhido não recebe estas formas de pagamento neste ponto de venda")
        return chosen
    if len(fits) == 1:
        return fits[0]
    if len(fits) > 1:
        raise TerminalChoiceError("Escolha o terminal (TPA / Express) por onde passou o pagamento")
    if any(bank_methods & set(t.payment_method_ids or []) for t in usable):
        # each bank method has its terminal, but not the same one: two banks for one document
        raise TerminalChoiceError("Um documento só pode passar por um terminal - pague a parte bancária com uma só forma de pagamento")
    return None
