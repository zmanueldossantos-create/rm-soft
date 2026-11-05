"""
Tesouraria - transfers between two bank accounts of the company (see app.models.bank_transfer).

  - create_bank_transfer: the money leaves the first account on its date. Within one bank it is on the second account
    the same day (DISPONIVEL); between two banks it stays em trânsito - in no account - until confirm_funds_available.
  - confirm_funds_available: «Fundos disponíveis» - the day the second bank shows the money; it enters that account.
  - cancel_bank_transfer: a mistake - never deleted; the statements keep the transfer and its reversal (today): the
    first account gets the money back, the second gives it back if it had received it.
transfer_lines gives the statement lines of one account (read by bank_treasury_service). The dates are internal entries:
in the active period or in the soft-closed one, never before an account's opening balance.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from app.models.bank_transfer import BankTransfer, BankTransferStatus
from app.models.company_bank_account import CompanyBankAccount
from app.models.user import User
from app.services.bank_treasury_service import (
    LUANDA, BankMovementError, _Line, _account_or_raise, _check_date_open,
)


class BankTransferNotFoundError(Exception):
    pass


async def _labels(db: AsyncSession, account_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """«BAI · 0012345678» for each account."""
    if not account_ids:
        return {}
    rows = (await db.execute(
        select(CompanyBankAccount.id, Bank.acronym, CompanyBankAccount.account_number)
        .join(Bank, Bank.id == CompanyBankAccount.bank_id).where(CompanyBankAccount.id.in_(account_ids))
    )).all()
    return {row[0]: f"{row[1]} · {row[2]}" for row in rows}


def _check_not_before_opening(account: CompanyBankAccount, day: date) -> None:
    if account.opening_date is not None and day < account.opening_date:
        raise BankMovementError(f"A data é anterior ao saldo inicial da conta ({account.opening_date.strftime('%d/%m/%Y')}) "
                                "- esse movimento já está no saldo inicial")


async def create_bank_transfer(
    db: AsyncSession, company_id: uuid.UUID, user: User, from_account_id: uuid.UUID, to_account_id: uuid.UUID,
    amount: float, transfer_date: date, reference: str | None = None, description: str | None = None,
) -> BankTransfer:
    """A transfer from one account of the company to another - see the module docstring. The first account may go
    below zero (the screen warns, the bank decides)."""
    if from_account_id == to_account_id:
        raise BankMovementError("Escolha duas contas diferentes")
    source = await _account_or_raise(db, company_id, from_account_id)
    target = await _account_or_raise(db, company_id, to_account_id)
    if not source.is_active or not target.is_active:
        raise BankMovementError("As duas contas têm de estar ativas")
    if source.currency_id != target.currency_id:
        raise BankMovementError("As duas contas têm de ter a mesma moeda")
    amount = round(float(amount), 2)
    if amount <= 0:
        raise BankMovementError("O valor tem de ser maior que zero")
    if transfer_date > date.today():
        raise BankMovementError("A data não pode ser futura")
    _check_not_before_opening(source, transfer_date)
    await _check_date_open(db, company_id, transfer_date)
    same_bank = source.bank_id == target.bank_id
    if same_bank:
        _check_not_before_opening(target, transfer_date)

    series = f"TRF{transfer_date.year}"
    # one numbering at a time per company and year: two transfers typed at once never get the same number
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"banktrf:{company_id}:{series}"})
    last = (await db.execute(select(func.max(BankTransfer.number)).where(
        BankTransfer.company_id == company_id, BankTransfer.series == series))).scalar_one()
    transfer = BankTransfer(
        company_id=company_id, series=series, number=(last or 0) + 1, from_account_id=source.id,
        to_account_id=target.id, amount=amount, transfer_date=transfer_date,
        available_date=transfer_date if same_bank else None,
        status=BankTransferStatus.DISPONIVEL if same_bank else BankTransferStatus.EM_TRANSITO,
        reference=(reference or "").strip() or None, description=(description or "").strip() or None,
        confirmed_by_user_id=user.id if same_bank else None, created_by_user_id=user.id,
    )
    db.add(transfer)
    await db.commit()
    await db.refresh(transfer)
    return transfer


async def _get_for_update(db: AsyncSession, company_id: uuid.UUID, transfer_id: uuid.UUID) -> BankTransfer:
    transfer = (await db.execute(select(BankTransfer).where(
        BankTransfer.id == transfer_id, BankTransfer.company_id == company_id).with_for_update())).scalar_one_or_none()
    if transfer is None:
        raise BankTransferNotFoundError("Transferência não encontrada")
    return transfer


async def confirm_funds_available(
    db: AsyncSession, company_id: uuid.UUID, transfer_id: uuid.UUID, user: User, available_date: date,
) -> BankTransfer:
    """«Fundos disponíveis»: the money of a transfer em trânsito is on the second account from available_date."""
    transfer = await _get_for_update(db, company_id, transfer_id)
    if transfer.status != BankTransferStatus.EM_TRANSITO:
        raise BankMovementError("Esta transferência não está em trânsito")
    if available_date > date.today():
        raise BankMovementError("A data não pode ser futura")
    if available_date < transfer.transfer_date:
        raise BankMovementError("Os fundos não podem chegar antes de a transferência sair "
                                f"({transfer.transfer_date.strftime('%d/%m/%Y')})")
    target = await _account_or_raise(db, company_id, transfer.to_account_id)
    _check_not_before_opening(target, available_date)
    await _check_date_open(db, company_id, available_date)
    transfer.status = BankTransferStatus.DISPONIVEL
    transfer.available_date = available_date
    transfer.confirmed_by_user_id = user.id
    await db.commit()
    await db.refresh(transfer)
    return transfer


async def cancel_bank_transfer(
    db: AsyncSession, company_id: uuid.UUID, transfer_id: uuid.UUID, user: User, reason: str,
) -> BankTransfer:
    """Cancels a transfer - see the module docstring: reversed today on the accounts it moved."""
    transfer = await _get_for_update(db, company_id, transfer_id)
    if transfer.status == BankTransferStatus.ANULADO:
        raise BankMovementError("Esta transferência já está anulada")
    reason = (reason or "").strip()
    if not reason:
        raise BankMovementError("Indique o motivo da anulação")
    await _check_date_open(db, company_id, datetime.now(LUANDA).date())
    transfer.status = BankTransferStatus.ANULADO
    transfer.cancel_reason = reason[:300]
    transfer.cancelled_at = datetime.now(timezone.utc)
    transfer.cancelled_by_user_id = user.id
    await db.commit()
    await db.refresh(transfer)
    return transfer


async def describe_transfers(db: AsyncSession, transfers: list[BankTransfer]) -> list[dict]:
    labels = await _labels(db, {t.from_account_id for t in transfers} | {t.to_account_id for t in transfers})
    return [{
        "id": t.id, "document": f"{t.series}/{t.number}", "from_account_id": t.from_account_id,
        "from_label": labels.get(t.from_account_id, ""), "to_account_id": t.to_account_id,
        "to_label": labels.get(t.to_account_id, ""), "amount": float(t.amount), "transfer_date": t.transfer_date,
        "available_date": t.available_date, "status": t.status.value, "reference": t.reference,
        "description": t.description,
    } for t in transfers]


async def list_transfers_in_transit(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """The transfers still on their way, oldest first - waiting for «Fundos disponíveis»."""
    transfers = (await db.execute(select(BankTransfer).where(
        BankTransfer.company_id == company_id, BankTransfer.status == BankTransferStatus.EM_TRANSITO,
    ).order_by(BankTransfer.transfer_date, BankTransfer.number))).scalars().all()
    return await describe_transfers(db, list(transfers))


async def transfer_lines(db: AsyncSession, company_id: uuid.UUID, account: CompanyBankAccount) -> list[_Line]:
    """The statement lines of the transfers of one account (it sent or received)."""
    transfers = (await db.execute(select(BankTransfer).where(
        BankTransfer.company_id == company_id,
        or_(BankTransfer.from_account_id == account.id, BankTransfer.to_account_id == account.id),
    ))).scalars().all()
    labels = await _labels(db, {t.from_account_id for t in transfers} | {t.to_account_id for t in transfers})
    lines: list[_Line] = []
    for t in transfers:
        document = f"{t.series}/{t.number}"
        amount = float(t.amount)
        cancelled = t.status == BankTransferStatus.ANULADO
        cancel_day = t.cancelled_at.astimezone(LUANDA).date() if cancelled and t.cancelled_at else None
        extra = [t.description, t.reference]
        if t.from_account_id == account.id:
            lines.append(_Line(
                day=t.transfer_date, at=t.created_at, document=document,
                description=" · ".join(filter(None, ["Transferência para " + labels.get(t.to_account_id, ""), *extra])),
                amount=-amount, transfer_id=None if cancelled else t.id,
                in_transit=t.status == BankTransferStatus.EM_TRANSITO,
            ))
            if cancel_day is not None:
                lines.append(_Line(day=cancel_day, at=t.cancelled_at, document=document,
                                   description=" · ".join(filter(None, ["Transferência", "Anulação", t.cancel_reason])),
                                   amount=amount))
        if t.to_account_id == account.id and t.available_date is not None:
            lines.append(_Line(
                day=t.available_date, at=t.created_at, document=document,
                description=" · ".join(filter(None, ["Transferência de " + labels.get(t.from_account_id, ""), *extra])),
                amount=amount, transfer_id=None if cancelled else t.id,
            ))
            if cancel_day is not None:
                lines.append(_Line(day=cancel_day, at=t.cancelled_at, document=document,
                                   description=" · ".join(filter(None, ["Transferência", "Anulação", t.cancel_reason])),
                                   amount=-amount))
    return lines


async def in_transit_by_account(db: AsyncSession, company_id: uuid.UUID) -> dict[uuid.UUID, float]:
    """For each account, the money on its way to it (transfers em trânsito)."""
    rows = (await db.execute(
        select(BankTransfer.to_account_id, func.sum(BankTransfer.amount)).where(
            BankTransfer.company_id == company_id, BankTransfer.status == BankTransferStatus.EM_TRANSITO,
        ).group_by(BankTransfer.to_account_id)
    )).all()
    return {row[0]: round(float(row[1]), 2) for row in rows}
