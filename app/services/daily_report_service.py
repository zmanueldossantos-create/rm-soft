"""
Daily cash register report ("brouillard de caixa") - a chronological journal of
every operation touching a given POS's drawer within a date range: sales (via the
cash sessions opened on that POS) and cash movements (transfers, entrada/saida
externa). Read-only, purely a reporting view - never mutates anything.

Scope decision: sales are included only when tied to a cash session on this POS
(Invoice.cash_session_id -> CashSession.pos_id) - an invoice created outside the
Caixa flow (e.g. via NovaFatura, no session) is a different kind of document and
not part of this POS's daily cash journal, even if it shares the same Activity.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.cash_session import CashSession
from app.models.cash_movement import CashMovement, CashMovementStatus, CashMovementType


async def get_daily_report(
    db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID, date_from: date, date_to: date,
) -> list[dict]:
    """
    Returns a chronological list of entries, each shaped as:
    {
        "type": "venda" | "movimento",
        "time": datetime,
        "business_date": date,
        "description": str,
        "amount": float,
        "direction": "entrada" | "saida",  # only for movements
        "reference": str,  # invoice series/number, or movement type label
    }
    """
    entries: list[dict] = []

    # The journal lists the money that actually moved in this POS: one line per payment recorded on a document of its
    # cash sessions. A Fatura billed later or a pro-forma has no payment, so no line. A credit note has a payment only
    # when money was explicitly given back from this cash point: that payment is negative, shown as an outgoing line.
    payments_result = await db.execute(
        select(Payment, Invoice, PaymentMethodCatalog.name, PaymentMethodCatalog.is_cash)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .join(CashSession, CashSession.id == Invoice.cash_session_id)
        .join(PaymentMethodCatalog, PaymentMethodCatalog.id == Payment.payment_method_id)
        .where(
            CashSession.company_id == company_id,
            CashSession.pos_id == pos_id,
            Invoice.business_date >= date_from,
            Invoice.business_date <= date_to,
        )
        .order_by(Payment.created_at)
    )
    invoice_type_labels = {"FACTURA": "FT", "FACTURA_RECIBO": "FR", "PRO_FORMA": "PF", "NOTA_CREDITO": "NC", "NOTA_DEBITO": "ND", "RECIBO": "RC"}
    for payment, inv, method_name, method_is_cash in payments_result.all():
        type_value = inv.invoice_type.value if hasattr(inv.invoice_type, "value") else str(inv.invoice_type)
        label = invoice_type_labels.get(type_value, type_value)
        is_refund = float(payment.amount) < 0
        entries.append({
            "type": "reembolso" if is_refund else "venda",
            "time": payment.created_at,
            "business_date": inv.business_date,
            "description": f"{label} {inv.series}/{inv.number} - {method_name}" + (" - Reembolso" if is_refund else ""),
            "amount": abs(float(payment.amount)),
            "direction": "saida" if is_refund else "entrada",
            "reference": f"{inv.series}/{inv.number}",
            "payment_method": method_name,  # totals by method on the movements report
            "is_cash": bool(method_is_cash),
        })

    movements_result = await db.execute(
        select(CashMovement).where(
            CashMovement.company_id == company_id,
            (CashMovement.source_pos_id == pos_id) | (CashMovement.destination_pos_id == pos_id),
            CashMovement.movement_date >= date_from,
            CashMovement.movement_date <= date_to,
        ).order_by(CashMovement.created_at)
    )
    for mov in movements_result.scalars().all():
        is_outgoing = mov.source_pos_id == pos_id
        label = {
            CashMovementType.TRANSFERENCIA: "Transferencia",
            CashMovementType.ENTRADA_EXTERNA: "Entrada externa",
            CashMovementType.SAIDA_EXTERNA: "Saida externa",
        }.get(mov.movement_type, str(mov.movement_type))
        entries.append({
            "type": "movimento",
            "time": mov.created_at,
            "business_date": mov.movement_date,
            # a transfer received but not confirmed is not in the drawer yet - said so on the line
            "description": label + (" (saida)" if is_outgoing else " (entrada)")
            + (" - por confirmar" if not is_outgoing and mov.status != CashMovementStatus.RECEBIDO else ""),
            "amount": float(mov.amount),
            "direction": "saida" if is_outgoing else "entrada",
            "reference": mov.description or label,
        })

    entries.sort(key=lambda e: e["time"])
    return entries
