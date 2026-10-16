"""
Pagamentos a fornecedores e conta corrente (point 3).

- what is owed on a supplier invoice: an invoice (FT) is owed until paid; a fatura-recibo or a talão de venda (FR, TV)
  was paid when issued; a credit note (NC) of the supplier lowers what is owed on the invoice it corrects. Owed = total
  - its active credit notes - its active payments, never below zero; overdue when still owed after its due date.
- pay: one payment (PAG2026/1) for invoices of ONE supplier, each with the amount it settles (never more than what is
  still owed on it). The method must allow payments; a bank method names the company's account; cash leaves a till -
  an automatic exit "Pagamento a fornecedor" of that till, in the same transaction (the till must be open, today).
- cancel (with a reason): the invoices are owed again; cash goes back into its till (an automatic entry - the till must be
  open). A purchase invoice with active payments is not cancelled (purchase_invoice_service).
- conta corrente: the supplier's documents in date order with the running balance (what the company owes it), from the
  balance before the period.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from app.models.cash_movement import CashMovementType
from app.models.cash_movement_reason import CashMovementReason
from app.models.company_bank_account import CompanyBankAccount
from app.models.movement_type import MovementDirection
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.point_of_sale import PointOfSale
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.models.supplier import Supplier
from app.models.supplier_payment import SupplierPayment, SupplierPaymentAllocation, SupplierPaymentStatus
from app.models.user import User
from app.services.cash_movement_service import (
    InsufficientFundsError, InvalidCashMovementError, ReasonDirectionMismatchError, SourcePosNotOpenError,
    create_cash_movement,
)
from app.services.point_of_sale_service import PosNotFoundError
from app.services.user_cash_point_access_service import CashPointAccessDeniedError

_TILL_ERRORS = (SourcePosNotOpenError, InsufficientFundsError, InvalidCashMovementError, ReasonDirectionMismatchError,
                PosNotFoundError, CashPointAccessDeniedError)

PAYMENT_REASON = "Pagamento a fornecedor"
REVERSAL_REASON = "Anulação de pagamento a fornecedor"
# the supplier documents that were paid when issued, and the one that corrects an invoice
PAID_ON_ISSUE = {"FR", "TV"}
PAYMENT_STATUS_LABELS = {"PENDENTE": "Pendente", "PARCIAL": "Parcial", "PAGA": "Paga"}


class SupplierPaymentError(Exception):
    """A payment that cannot be made or changed as asked (the message says why)."""


class SupplierPaymentNotFoundError(Exception):
    pass


def _money(value: float) -> float:
    return round(float(value) + 0.0, 2)


def reference(payment: SupplierPayment) -> str:
    return f"{payment.series}/{payment.number}"


async def invoice_balances(db: AsyncSession, invoices) -> dict:
    """{invoice id: {paid, credited, due, payment_status, overdue}} for the given purchase invoices - an NC or a cancelled
    registration owes nothing (payment_status None)."""
    invoices = list(invoices)
    ids = [i.id for i in invoices]
    if not ids:
        return {}
    credited = dict((await db.execute(
        select(PurchaseInvoice.reference_invoice_id, func.sum(PurchaseInvoice.total))
        .where(PurchaseInvoice.reference_invoice_id.in_(ids), PurchaseInvoice.purchase_type == "NC",
               PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA)
        .group_by(PurchaseInvoice.reference_invoice_id)
    )).all())
    paid = dict((await db.execute(
        select(SupplierPaymentAllocation.purchase_invoice_id, func.sum(SupplierPaymentAllocation.amount))
        .join(SupplierPayment, SupplierPayment.id == SupplierPaymentAllocation.payment_id)
        .where(SupplierPaymentAllocation.purchase_invoice_id.in_(ids), SupplierPayment.status == SupplierPaymentStatus.REGISTADO)
        .group_by(SupplierPaymentAllocation.purchase_invoice_id)
    )).all())
    today = date.today()
    result = {}
    for inv in invoices:
        if inv.status != PurchaseInvoiceStatus.REGISTADA or inv.purchase_type == "NC":
            result[inv.id] = {"paid": 0.0, "credited": 0.0, "due": 0.0, "payment_status": None, "overdue": False}
            continue
        total, cred = float(inv.total), float(credited.get(inv.id) or 0)
        if inv.purchase_type in PAID_ON_ISSUE:  # paid when issued
            result[inv.id] = {"paid": _money(total - cred), "credited": _money(cred), "due": 0.0, "payment_status": "PAGA",
                              "overdue": False}
            continue
        p = float(paid.get(inv.id) or 0)
        due = max(_money(total - cred - p), 0.0)
        status = "PAGA" if due <= 0.005 else ("PARCIAL" if p > 0.005 or cred > 0.005 else "PENDENTE")
        result[inv.id] = {"paid": _money(p), "credited": _money(cred), "due": due, "payment_status": status,
                          "overdue": due > 0.005 and inv.due_date is not None and inv.due_date < today}
    return result


async def _reason(db: AsyncSession, company_id: uuid.UUID, name: str, direction: MovementDirection) -> CashMovementReason:
    """The till movement reason the payments use - created for the company the first time."""
    reason = (await db.execute(select(CashMovementReason).where(
        CashMovementReason.company_id == company_id, CashMovementReason.name == name))).scalar_one_or_none()
    if reason is None:
        reason = CashMovementReason(company_id=company_id, name=name, direction=direction, is_active=True)
        db.add(reason)
        await db.flush()
    return reason


async def _next_number(db: AsyncSession, company_id: uuid.UUID, series: str) -> int:
    last = (await db.execute(select(func.max(SupplierPayment.number)).where(
        SupplierPayment.company_id == company_id, SupplierPayment.series == series))).scalar_one()
    return (last or 0) + 1


async def create_supplier_payment(
    db: AsyncSession, company_id: uuid.UUID, user: User, supplier_id: uuid.UUID, allocations: list[dict],
    payment_method_id: uuid.UUID, payment_date: date | None = None, bank_account_id: uuid.UUID | None = None,
    pos_id: uuid.UUID | None = None, reference_text: str | None = None, notes: str | None = None,
) -> SupplierPayment:
    """allocations: [{purchase_invoice_id, amount}] - invoices (FT) of the supplier, each amount at most what is owed."""
    today = date.today()
    payment_date = payment_date or today
    if payment_date > today:
        raise SupplierPaymentError("A data do pagamento não pode ser futura")
    supplier = (await db.execute(select(Supplier).where(
        Supplier.id == supplier_id, Supplier.company_id == company_id))).scalar_one_or_none()
    if supplier is None:
        raise SupplierPaymentError("Escolha o fornecedor")
    wanted: dict[uuid.UUID, float] = {}
    for a in allocations or []:
        amount = _money(a.get("amount") or 0)
        if amount > 0:
            key = uuid.UUID(str(a["purchase_invoice_id"]))
            wanted[key] = _money(wanted.get(key, 0) + amount)
    if not wanted:
        raise SupplierPaymentError("Indique o valor a pagar de pelo menos uma fatura")
    invoices = (await db.execute(select(PurchaseInvoice).where(
        PurchaseInvoice.id.in_(list(wanted)), PurchaseInvoice.company_id == company_id).with_for_update())).scalars().all()
    if len(invoices) != len(wanted):
        raise SupplierPaymentError("Fatura de compra não encontrada")
    balances = await invoice_balances(db, invoices)
    for inv in invoices:
        label = f"{inv.series}/{inv.number} ({inv.supplier_document})"
        if inv.supplier_id != supplier.id:
            raise SupplierPaymentError(f"A fatura {label} não é deste fornecedor")
        if inv.status != PurchaseInvoiceStatus.REGISTADA:
            raise SupplierPaymentError(f"A fatura {label} está anulada")
        if inv.purchase_type != "FT":
            raise SupplierPaymentError(f"O documento {label} não se paga: só uma fatura (FT) fica em dívida")
        due = balances[inv.id]["due"]
        if wanted[inv.id] > due + 0.005:
            raise SupplierPaymentError(f"O valor da fatura {label} excede o que está em dívida ({due:,.2f} Kz)".replace(",", " "))
    amount = _money(sum(wanted.values()))

    method = (await db.execute(select(PaymentMethodCatalog).where(PaymentMethodCatalog.id == payment_method_id))).scalar_one_or_none()
    if method is None or not method.is_active:
        raise SupplierPaymentError("Escolha o método de pagamento")
    if not method.allows_payment:
        raise SupplierPaymentError(f"O método {method.name} não pode ser usado para pagamentos")
    if method.uses_bank_account:
        if bank_account_id is None or (await db.execute(select(CompanyBankAccount.id).where(
                CompanyBankAccount.id == bank_account_id, CompanyBankAccount.company_id == company_id,
                CompanyBankAccount.is_active.is_(True)))).scalar_one_or_none() is None:
            raise SupplierPaymentError("Escolha a conta bancária de onde sai o pagamento")
    else:
        bank_account_id = None
    if method.is_cash:
        if pos_id is None:
            raise SupplierPaymentError("Escolha a caixa de onde sai o numerário")
        if payment_date != today:
            raise SupplierPaymentError("Um pagamento em numerário sai hoje da caixa - a data deve ser a de hoje")
    else:
        pos_id = None

    series = f"PAG{payment_date.year}"
    payment = SupplierPayment(
        company_id=company_id, supplier_id=supplier.id, series=series, number=await _next_number(db, company_id, series),
        payment_date=payment_date, amount=amount, payment_method_id=method.id, bank_account_id=bank_account_id,
        pos_id=pos_id, reference=(" ".join((reference_text or "").split()) or None), notes=(notes or None),
        status=SupplierPaymentStatus.REGISTADO, created_by_user_id=user.id,
    )
    db.add(payment)
    await db.flush()
    for inv_id, value in wanted.items():
        db.add(SupplierPaymentAllocation(payment_id=payment.id, purchase_invoice_id=inv_id, amount=value))
    if pos_id is not None:  # the cash leaves the till - the movement commits the payment with it, or nothing is kept
        reason = await _reason(db, company_id, PAYMENT_REASON, MovementDirection.SAIDA)
        try:
            movement = await create_cash_movement(
                db, company_id, CashMovementType.SAIDA_EXTERNA, user, amount, source_pos_id=pos_id, reason_id=reason.id,
                movement_date=payment_date, description=f"{reference(payment)} - {supplier.name}"[:300],  # the reason says the rest
            )
        except _TILL_ERRORS as e:  # the till is closed, short of cash, or not the user's: nothing is kept
            await db.rollback()
            raise SupplierPaymentError(str(e))
        except Exception:
            await db.rollback()
            raise
        payment = (await db.execute(select(SupplierPayment).where(SupplierPayment.supplier_id == supplier.id,
                                                                   SupplierPayment.series == series,
                                                                   SupplierPayment.number == payment.number,
                                                                   SupplierPayment.company_id == company_id))).scalar_one()
        payment.cash_movement_id = movement.id
    await db.commit()
    await db.refresh(payment)
    return payment


async def _get(db: AsyncSession, company_id: uuid.UUID, payment_id: uuid.UUID) -> SupplierPayment:
    payment = (await db.execute(select(SupplierPayment).where(
        SupplierPayment.id == payment_id, SupplierPayment.company_id == company_id))).scalar_one_or_none()
    if payment is None:
        raise SupplierPaymentNotFoundError("Pagamento não encontrado")
    return payment


async def cancel_supplier_payment(db: AsyncSession, company_id: uuid.UUID, payment_id: uuid.UUID, user: User,
                                  reason: str) -> SupplierPayment:
    payment = await _get(db, company_id, payment_id)
    if payment.status == SupplierPaymentStatus.ANULADO:
        raise SupplierPaymentError("Este pagamento já está anulado")
    reason = " ".join((reason or "").split())
    if not reason:
        raise SupplierPaymentError("Indique o motivo da anulação")
    payment_ref, pos_id, amount = reference(payment), payment.pos_id, float(payment.amount)
    payment.status = SupplierPaymentStatus.ANULADO
    payment.cancel_reason = reason[:300]
    payment.cancelled_at = datetime.now(timezone.utc)
    payment.cancelled_by_user_id = user.id
    if pos_id is not None:  # the cash goes back into the till it left
        entry = await _reason(db, company_id, REVERSAL_REASON, MovementDirection.ENTRADA)
        from app.services.cash_session_service import get_open_session
        if await get_open_session(db, company_id, pos_id) is None:
            await db.rollback()
            raise SupplierPaymentError("A caixa de onde saiu o numerário não tem sessão aberta - abra-a para o dinheiro voltar")
        try:
            movement = await create_cash_movement(
                db, company_id, CashMovementType.ENTRADA_EXTERNA, user, amount, destination_pos_id=pos_id,
                reason_id=entry.id, description=f"{payment_ref}: {reason}"[:300],
            )
        except _TILL_ERRORS as e:
            await db.rollback()
            raise SupplierPaymentError(str(e))
        except Exception:
            await db.rollback()
            raise
        payment = await _get(db, company_id, payment_id)
        payment.reversal_movement_id = movement.id
    await db.commit()
    await db.refresh(payment)
    return payment


async def _names(db: AsyncSession, model, ids, column="name") -> dict:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    return dict((await db.execute(select(model.id, getattr(model, column)).where(model.id.in_(ids)))).all())


async def _summaries(db: AsyncSession, payments) -> list[dict]:
    suppliers = await _names(db, Supplier, {p.supplier_id for p in payments})
    methods = await _names(db, PaymentMethodCatalog, {p.payment_method_id for p in payments})
    tills = await _names(db, PointOfSale, {p.pos_id for p in payments})
    accounts = {}
    bank_ids = [p.bank_account_id for p in payments if p.bank_account_id]
    if bank_ids:
        accounts = {i: f"{acr} - {number}" for i, number, acr in (await db.execute(
            select(CompanyBankAccount.id, CompanyBankAccount.account_number, Bank.acronym)
            .join(Bank, Bank.id == CompanyBankAccount.bank_id).where(CompanyBankAccount.id.in_(bank_ids)))).all()}
    return [{
        "id": p.id, "reference": reference(p), "status": p.status.value, "payment_date": p.payment_date,
        "supplier_id": p.supplier_id, "supplier_name": suppliers.get(p.supplier_id), "amount": float(p.amount),
        "method": methods.get(p.payment_method_id), "source": tills.get(p.pos_id) or accounts.get(p.bank_account_id),
        "reference_text": p.reference, "created_at": p.created_at,
    } for p in payments]


async def list_supplier_payments(db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID | None = None,
                                 status: str | None = None, date_from: date | None = None,
                                 date_to: date | None = None) -> list[dict]:
    query = select(SupplierPayment).where(SupplierPayment.company_id == company_id)
    if supplier_id:
        query = query.where(SupplierPayment.supplier_id == supplier_id)
    if status:
        query = query.where(SupplierPayment.status == SupplierPaymentStatus(status))
    if date_from:
        query = query.where(SupplierPayment.payment_date >= date_from)
    if date_to:
        query = query.where(SupplierPayment.payment_date <= date_to)
    payments = (await db.execute(query.order_by(SupplierPayment.payment_date.desc(), SupplierPayment.number.desc()))).scalars().all()
    return await _summaries(db, payments)


async def get_supplier_payment(db: AsyncSession, company_id: uuid.UUID, payment_id: uuid.UUID) -> dict:
    payment = await _get(db, company_id, payment_id)
    summary = (await _summaries(db, [payment]))[0]
    rows = (await db.execute(
        select(SupplierPaymentAllocation, PurchaseInvoice)
        .join(PurchaseInvoice, PurchaseInvoice.id == SupplierPaymentAllocation.purchase_invoice_id)
        .where(SupplierPaymentAllocation.payment_id == payment.id).order_by(PurchaseInvoice.document_date, PurchaseInvoice.number)
    )).all()
    users = await _names(db, User, {payment.created_by_user_id, payment.cancelled_by_user_id}, "full_name")
    supplier = (await db.execute(select(Supplier).where(Supplier.id == payment.supplier_id))).scalar_one()
    return {
        **summary, "supplier_nif": supplier.nif, "notes": payment.notes,
        "created_by": users.get(payment.created_by_user_id), "cancelled_by": users.get(payment.cancelled_by_user_id),
        "cancel_reason": payment.cancel_reason, "cancelled_at": payment.cancelled_at,
        "allocations": [{
            "purchase_invoice_id": inv.id, "reference": f"{inv.series}/{inv.number}", "supplier_document": inv.supplier_document,
            "document_date": inv.document_date, "invoice_total": float(inv.total), "amount": float(a.amount),
        } for a, inv in rows],
    }


async def supplier_balances(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """{supplier id: what the company owes it} - its invoices (FT) less their credit notes and the active payments."""
    invoices = (await db.execute(select(PurchaseInvoice).where(
        PurchaseInvoice.company_id == company_id, PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA,
        PurchaseInvoice.purchase_type == "FT"))).scalars().all()
    balances = await invoice_balances(db, invoices)
    owed: dict = {}
    for inv in invoices:
        owed[inv.supplier_id] = _money(owed.get(inv.supplier_id, 0) + balances[inv.id]["due"])
    return owed


async def supplier_statement(db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID,
                             date_from: date | None = None, date_to: date | None = None) -> dict:
    """
    The conta corrente: the supplier's documents in date order - an invoice raises what the company owes (crédito),
    a credit note or a payment lowers it (débito); a fatura-recibo / talão is paid on issue (both sides). The balance
    before date_from opens the statement.
    """
    supplier = (await db.execute(select(Supplier).where(
        Supplier.id == supplier_id, Supplier.company_id == company_id))).scalar_one_or_none()
    if supplier is None:
        raise SupplierPaymentNotFoundError("Fornecedor não encontrado")
    entries = []
    invoices = (await db.execute(select(PurchaseInvoice).where(
        PurchaseInvoice.company_id == company_id, PurchaseInvoice.supplier_id == supplier_id,
        PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA))).scalars().all()
    for inv in invoices:
        doc = inv.supplier_document  # as printed by the supplier (FT A/123) - the type is in the description
        key = (inv.document_date, inv.created_at)
        if inv.purchase_type == "NC":
            entries.append({"date": inv.document_date, "sort": key, "document": doc, "internal": f"{inv.series}/{inv.number}",
                            "description": "Nota de crédito", "debit": float(inv.total), "credit": 0.0})
            continue
        entries.append({"date": inv.document_date, "sort": key, "document": doc, "internal": f"{inv.series}/{inv.number}",
                        "description": {"FT": "Fatura", "FR": "Fatura-recibo", "TV": "Talão de venda"}.get(inv.purchase_type, "Fatura"),
                        "debit": 0.0, "credit": float(inv.total)})
        if inv.purchase_type in PAID_ON_ISSUE:
            entries.append({"date": inv.document_date, "sort": (inv.document_date, inv.created_at, 1), "document": doc,
                            "internal": f"{inv.series}/{inv.number}", "description": "Pago na emissão",
                            "debit": float(inv.total), "credit": 0.0})
    payments = (await db.execute(select(SupplierPayment).where(
        SupplierPayment.company_id == company_id, SupplierPayment.supplier_id == supplier_id,
        SupplierPayment.status == SupplierPaymentStatus.REGISTADO))).scalars().all()
    methods = await _names(db, PaymentMethodCatalog, {p.payment_method_id for p in payments})
    for p in payments:
        entries.append({"date": p.payment_date, "sort": (p.payment_date, p.created_at), "document": reference(p),
                        "internal": reference(p), "description": f"Pagamento ({methods.get(p.payment_method_id, '-')})"
                        + (f" - {p.reference}" if p.reference else ""), "debit": float(p.amount), "credit": 0.0})
    entries.sort(key=lambda e: (e["sort"][0], e["sort"][1] or datetime.min.replace(tzinfo=timezone.utc), e["sort"][2] if len(e["sort"]) > 2 else 0))
    opening = _money(sum(e["credit"] - e["debit"] for e in entries if date_from and e["date"] < date_from))
    balance, lines = opening, []
    for e in entries:
        if (date_from and e["date"] < date_from) or (date_to and e["date"] > date_to):
            continue
        balance = _money(balance + e["credit"] - e["debit"])
        lines.append({k: e[k] for k in ("date", "document", "internal", "description", "debit", "credit")} | {"balance": balance})
    return {
        "supplier_id": supplier.id, "supplier_name": supplier.name, "supplier_nif": supplier.nif,
        "date_from": date_from, "date_to": date_to, "opening_balance": opening, "lines": lines,
        "total_debit": _money(sum(l["debit"] for l in lines)), "total_credit": _money(sum(l["credit"] for l in lines)),
        "closing_balance": balance,
    }
