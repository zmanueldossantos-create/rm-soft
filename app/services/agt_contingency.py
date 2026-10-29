"""
Contingência (Faturação Eletrónica): while the AGT cannot be reached, the company's new documents take its C series
(asked to the AGT beforehand, while there was a connection); they wait in the queue and go, in their order, as soon as
the AGT answers again - then the documents are numbered on the N series again.

- automatic: FAILURES_TO_SWITCH network failures in a row, or the AGT unreachable for MINUTES_TO_SWITCH minutes (every
  call to the AGT says whether it got an answer: note_failure / note_success, from app.services.agt_client.call);
  off at the first answer of the AGT;
- manual: the gestor switches it on (an outage he knows of - the internet line cut...), and off; the AGT answering
  does not switch a manual contingência off;
- without a valid C series the documents keep the N series (a sale is never refused for it): they wait in the queue
  all the same, the screen says that a C series is missing;
- the 18 h alert: a document still not validated 18 h after it was issued (the AGT penalises after 24 h) is reported
  to the gestor once (notification AGT_ATRASO) and on the dashboard.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.document_series import ContingencyIndicator, DocumentSeries
from app.models.invoice import Invoice, InvoiceStatus

log = logging.getLogger(__name__)

FAILURES_TO_SWITCH = 3
MINUTES_TO_SWITCH = 5
LATE_HOURS = 18
WAITING = (InvoiceStatus.PENDENTE, InvoiceStatus.POR_ENVIAR, InvoiceStatus.ENVIADA)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def in_contingency(db: AsyncSession, company_id: uuid.UUID) -> bool:
    company = await db.get(Company, company_id)
    return bool(company is not None and company.agt_contingency)


async def _notify(db: AsyncSession, company_id: uuid.UUID, event: str, text: str) -> None:
    from app.services.notification_service import notify
    await notify(db, company_id, event, text)


async def note_failure(db: AsyncSession, company_id: uuid.UUID) -> bool:
    """A call to the AGT got no answer. Returns True when this failure switched the company into contingência."""
    company = await db.get(Company, company_id)
    if company is None:
        return False
    now = _now()
    company.agt_net_failures = (company.agt_net_failures or 0) + 1
    company.agt_first_failure_at = company.agt_first_failure_at or now
    switched = False
    if not company.agt_contingency and (
            company.agt_net_failures >= FAILURES_TO_SWITCH
            or now - company.agt_first_failure_at >= timedelta(minutes=MINUTES_TO_SWITCH)):
        company.agt_contingency, company.agt_contingency_manual, company.agt_contingency_since = True, False, now
        switched = True
        await _notify(db, company_id, "AGT_CONTINGENCIA",
                      "A AGT não responde: os novos documentos passam para a série de contingência e ficam em espera - "
                      "seguem sozinhos quando a ligação voltar.")
    await db.commit()
    return switched


async def note_success(db: AsyncSession, company_id: uuid.UUID) -> bool:
    """The AGT answered. Returns True when this ended an automatic contingência."""
    company = await db.get(Company, company_id)
    if company is None:
        return False
    company.agt_net_failures, company.agt_first_failure_at, company.agt_last_ok_at = 0, None, _now()
    ended = False
    if company.agt_contingency and not company.agt_contingency_manual:
        company.agt_contingency, company.agt_contingency_since = False, None
        ended = True
        await _notify(db, company_id, "AGT_CONTINGENCIA",
                      "A AGT voltou a responder: fim da contingência - os documentos em espera são enviados por ordem.")
    await db.commit()
    return ended


async def set_manual(db: AsyncSession, company: Company, on: bool) -> None:
    """The gestor's switch: on = contingência until he switches it off; off = back to normal (the queue goes on)."""
    company.agt_contingency, company.agt_contingency_manual = on, on
    company.agt_contingency_since = _now() if on else None
    if not on:
        company.agt_net_failures, company.agt_first_failure_at = 0, None
    await db.commit()


async def has_valid_c_series(db: AsyncSession, company_id: uuid.UUID) -> bool:
    now = _now()
    rows = (await db.execute(select(DocumentSeries).where(
        DocumentSeries.company_id == company_id, DocumentSeries.issuance_mode == "ELETRONICA",
        DocumentSeries.is_active.is_(True), DocumentSeries.year == now.year,
        DocumentSeries.contingency_indicator == ContingencyIndicator.CONTINGENCIA))).scalars().all()
    return any((r.series_start_ts is None or r.series_start_ts <= now) and (r.series_end_ts is None or now <= r.series_end_ts)
               and (r.agt_status or "") != "F" for r in rows)


async def status(db: AsyncSession, company: Company) -> dict:
    """The screen's view: the link to the AGT, the contingência, what waits and what is late."""
    late_limit = _now() - timedelta(hours=LATE_HOURS)
    waiting, oldest = (await db.execute(select(func.count(Invoice.id), func.min(Invoice.created_at)).where(
        Invoice.company_id == company.id, Invoice.issuance_mode == "ELETRONICA",
        Invoice.status.in_(WAITING)))).one()
    late = (await db.execute(select(func.count(Invoice.id)).where(
        Invoice.company_id == company.id, Invoice.issuance_mode == "ELETRONICA", Invoice.status.in_(WAITING),
        Invoice.created_at < late_limit))).scalar_one()
    return {
        "contingency": company.agt_contingency, "manual": company.agt_contingency_manual,
        "since": company.agt_contingency_since, "last_ok_at": company.agt_last_ok_at,
        "failures": company.agt_net_failures, "has_c_series": await has_valid_c_series(db, company.id),
        "waiting": waiting, "oldest_waiting_at": oldest, "late": late, "late_hours": LATE_HOURS,
    }


async def check_late(db: AsyncSession, now: datetime | None = None) -> int:
    """The documents still not validated 18 h after they were issued: the gestor told once per document (one message
    per company). Returns how many documents were reported."""
    now = now or _now()
    rows = (await db.execute(select(Invoice).where(
        Invoice.issuance_mode == "ELETRONICA", Invoice.status.in_(WAITING),
        Invoice.created_at < now - timedelta(hours=LATE_HOURS), Invoice.agt_late_notified_at.is_(None))
        .order_by(Invoice.created_at).limit(500))).scalars().all()
    by_company: dict[uuid.UUID, list[Invoice]] = {}
    for invoice in rows:
        by_company.setdefault(invoice.company_id, []).append(invoice)
    for company_id, invoices in by_company.items():
        first = invoices[0]
        await _notify(db, company_id, "AGT_ATRASO",
                      f"{len(invoices)} documento(s) ainda não validado(s) pela AGT há mais de {LATE_HOURS} h "
                      f"(o mais antigo: {first.series}/{first.number}). A AGT penaliza a partir das 24 h - verifique a "
                      "ligação à internet e a configuração da Faturação Eletrónica.")
        for invoice in invoices:
            invoice.agt_late_notified_at = now
    await db.commit()
    return len(rows)
