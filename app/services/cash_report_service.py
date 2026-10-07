"""
Cash reports: the figures of a till session's closing report - who, when, what was received by payment method,
which documents, the movements, and the closing (expected, counted, difference, reason). The PDF is drawn by
app.utils.cash_report_pdf. Always rebuilt from what is recorded, so a reprint is identical to the first print.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.cash_session import CashSessionStatus
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.user import User
from app.services.cash_session_service import get_session_or_raise, get_session_summary
from app.services.point_of_sale_service import get_pos_or_raise


class SessionNotClosedError(Exception):
    """The closing report exists only for a closed session."""
    pass


DOCUMENT_LABELS = {
    "FACTURA": "Factura", "FACTURA_RECIBO": "Factura/Recibo", "NOTA_CREDITO": "Nota de crédito",
    "NOTA_DEBITO": "Nota de débito", "RECIBO": "Recibo", "PRO_FORMA": "Factura pro-forma",
}


def _user_label(user: User | None) -> str:
    if user is None:
        return "-"
    for attr in ("full_name", "name", "phone_number", "phone"):
        value = getattr(user, attr, None)
        if value:
            return str(value)
    return "-"


async def get_closing_report_data(db: AsyncSession, company_id: uuid.UUID, session_id: uuid.UUID) -> dict:
    session = await get_session_or_raise(db, company_id, session_id)
    if session.status != CashSessionStatus.FECHADA:
        raise SessionNotClosedError("O relatorio de fecho so existe para uma sessao de caixa fechada")
    pos = await get_pos_or_raise(db, company_id, session.pos_id)
    activity = (await db.execute(select(Activity).where(Activity.id == pos.activity_id))).scalar_one()
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one()
    user_ids = [u for u in (session.opened_by_user_id, session.closed_by_user_id) if u]
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()}

    rows = await db.execute(
        select(Invoice.invoice_type, func.count(), func.coalesce(func.sum(Invoice.total), 0))
        .where(Invoice.cash_session_id == session.id)
        .group_by(Invoice.invoice_type)
    )
    documents = []
    for doc_type, count, total in rows.all():
        code = getattr(doc_type, "value", doc_type)
        documents.append({"type": code, "label": DOCUMENT_LABELS.get(code, str(code)), "count": int(count),
                          "total": round(float(total), 2)})
    documents.sort(key=lambda d: d["label"])

    return {
        "company": {
            "name": company.name, "nif": company.nif, "address": getattr(company, "address", None),
            "phone_number": getattr(company, "phone_number", None),
            "phone_number_2": getattr(company, "phone_number_2", None),
            "logo_path": getattr(company, "logo_path", None),
        },
        "pos_name": pos.name,
        "activity_name": activity.name,
        "business_date": session.business_date,
        "opened_at": session.opened_at,
        "opened_by": _user_label(users.get(session.opened_by_user_id)),
        "closed_at": session.closed_at,
        "closed_by": _user_label(users.get(session.closed_by_user_id)),
        "summary": await get_session_summary(db, company_id, session.pos_id, session),
        "documents": documents,
        "counted": round(float(session.closing_amount_counted), 2),
        "difference": round(float(session.closing_difference), 2),
        "notes": session.closing_notes,
    }
