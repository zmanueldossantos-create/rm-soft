"""
Histórico dos recursos - every use of a room, a table or a practitioner over a period, for every sector with
resources, and a summary per resource (uses, occupied time, revenue, cancellations, no-shows).

A read over existing data only, nothing stored:
- a booking (Booking) in progress or concluded is one use - a hotel stay (it has a stay account), a prepaid passage (Entrada: its own
  invoice, then a real departure), a marcação charged at the till (its own invoice), or a plain reservation;
  cancelled and no-show bookings are listed too, never counted as uses, and a pending or confirmed one is only
  planned (counted apart, without time);
- an open account on a resource without a booking (a restaurant or bar table) is one use, from its opening to its
  closing.

Revenue is what the documents of these uses brought in: their total (VAT included) minus the credit notes issued
against them - a marcação refunded by a full credit note brings nothing.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceType
from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.resource import Resource

# what a use is, for the screen's label
KIND_STAY = "ESTADIA"          # a hotel stay: check-in, an account, paid at the till
KIND_PASSAGE = "PASSAGEM"      # a prepaid passage (Entrada), then its real departure
KIND_CHARGED = "MARCACAO"      # a marcação charged at the till (Cobrar)
KIND_BOOKING = "RESERVA"       # a reservation without a document of its own
KIND_ACCOUNT = "CONTA"         # an account opened on the resource without a booking (a table)

NOT_A_USE = (BookingStatus.CANCELADA, BookingStatus.NO_SHOW)
# a reservation still to come (or never closed): planned, not a use yet - it counts neither time nor revenue
PLANNED = (BookingStatus.PENDENTE, BookingStatus.CONFIRMADA)


def _minutes(start: datetime, end: datetime | None) -> int:
    if end is None or end <= start:
        return 0
    return int((end - start).total_seconds() // 60)


async def get_resource_history(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
    now: datetime | None = None,
) -> dict:
    """{entries: [...], summary: [...]} - the uses that started in [date_from, date_to], most recent first, and one
    summary row per resource of the activity (resources without any use in the period included, at zero)."""
    now = now or datetime.now(timezone.utc)

    resources_query = select(Resource).where(Resource.company_id == company_id)
    if activity_id is not None:
        resources_query = resources_query.where(Resource.activity_id == activity_id)
    if resource_id is not None:
        resources_query = resources_query.where(Resource.id == resource_id)
    resources = {r.id: r for r in (await db.execute(resources_query.order_by(Resource.name))).scalars().all()}
    if not resources:
        return {"entries": [], "summary": []}

    bookings_query = select(Booking).where(Booking.company_id == company_id, Booking.resource_id.in_(list(resources)))
    accounts_query = select(OpenAccount).where(
        OpenAccount.company_id == company_id, OpenAccount.resource_id.in_(list(resources)), OpenAccount.booking_id.is_(None),
    )
    if date_from is not None:
        bookings_query = bookings_query.where(Booking.starts_at >= date_from)
        accounts_query = accounts_query.where(OpenAccount.opened_at >= date_from)
    if date_to is not None:
        bookings_query = bookings_query.where(Booking.starts_at <= date_to)
        accounts_query = accounts_query.where(OpenAccount.opened_at <= date_to)
    bookings = list((await db.execute(bookings_query)).scalars().all())
    accounts = list((await db.execute(accounts_query)).scalars().all())

    # the stay account of each booking (a hotel stay) - its invoice is the stay's document
    stay_accounts = {}
    if bookings:
        for account in (await db.execute(
            select(OpenAccount).where(OpenAccount.booking_id.in_([b.id for b in bookings]))
        )).scalars().all():
            stay_accounts[account.booking_id] = account

    invoice_ids = {b.invoice_id for b in bookings if b.invoice_id} | {a.invoice_id for a in stay_accounts.values() if a.invoice_id} \
        | {a.invoice_id for a in accounts if a.invoice_id}
    invoices, credited = {}, defaultdict(float)
    if invoice_ids:
        invoices = {i.id: i for i in (await db.execute(select(Invoice).where(Invoice.id.in_(invoice_ids)))).scalars().all()}
        for reference_id, total in (await db.execute(
            select(Invoice.reference_invoice_id, func.sum(Invoice.total)).where(
                Invoice.reference_invoice_id.in_(invoice_ids), Invoice.invoice_type == InvoiceType.NOTA_CREDITO,
            ).group_by(Invoice.reference_invoice_id)
        )).all():
            credited[reference_id] = float(total)

    customer_ids = {b.customer_id for b in bookings if b.customer_id} | {a.customer_id for a in accounts if a.customer_id}
    customers = dict((await db.execute(
        select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
    )).all()) if customer_ids else {}

    def document(invoice_id):
        invoice = invoices.get(invoice_id)
        if invoice is None:
            return {"invoice_id": None, "invoice_label": None, "invoice_total": None, "credited": 0.0, "revenue": 0.0}
        total = float(invoice.total)
        return {"invoice_id": invoice.id, "invoice_label": f"{invoice.series}/{invoice.number}", "invoice_total": total,
                "credited": round(credited.get(invoice.id, 0.0), 2), "revenue": round(total - credited.get(invoice.id, 0.0), 2)}

    entries = []
    for b in bookings:
        account = stay_accounts.get(b.id)
        if account is not None:
            kind, invoice_id = KIND_STAY, account.invoice_id
        elif b.invoice_id is not None and (b.checked_out_at is not None or b.status == BookingStatus.EM_CURSO):
            kind, invoice_id = KIND_PASSAGE, b.invoice_id
        elif b.invoice_id is not None:
            kind, invoice_id = KIND_CHARGED, b.invoice_id
        else:
            kind, invoice_id = KIND_BOOKING, None
        if b.status in NOT_A_USE or b.status in PLANNED:
            occupied_until = None
        elif b.checked_out_at is not None:
            occupied_until = b.checked_out_at
        elif b.status == BookingStatus.EM_CURSO:
            occupied_until = max(now, b.ends_at)
        else:
            occupied_until = b.ends_at
        overstay_end = b.checked_out_at or (now if b.status == BookingStatus.EM_CURSO else None)
        entries.append({
            "kind": kind, "booking_id": b.id, "account_id": account.id if account else None,
            "resource_id": b.resource_id, "resource_name": resources[b.resource_id].name,
            "customer_name": customers.get(b.customer_id), "guest_name": b.guest_name, "party_size": b.party_size,
            "starts_at": b.starts_at, "ends_at": b.ends_at, "real_end_at": b.checked_out_at,
            "overstay_minutes": _minutes(b.ends_at, overstay_end) if overstay_end else 0,
            "occupied_minutes": _minutes(b.starts_at, occupied_until),
            "status": b.status.value, **document(invoice_id),
        })
    for a in accounts:
        entries.append({
            "kind": KIND_ACCOUNT, "booking_id": None, "account_id": a.id,
            "resource_id": a.resource_id, "resource_name": resources[a.resource_id].name,
            "customer_name": customers.get(a.customer_id), "guest_name": None, "party_size": None,
            "starts_at": a.opened_at, "ends_at": a.closed_at, "real_end_at": a.closed_at, "overstay_minutes": 0,
            "occupied_minutes": _minutes(a.opened_at, a.closed_at or now),
            "status": "EM_CURSO" if a.status == OpenAccountStatus.ABERTA else "CONCLUIDA", **document(a.invoice_id),
        })
    entries.sort(key=lambda e: e["starts_at"], reverse=True)

    totals = {rid: {"resource_id": rid, "resource_name": r.name, "uses": 0, "occupied_minutes": 0, "revenue": 0.0,
                    "cancelled": 0, "no_show": 0, "planned": 0} for rid, r in resources.items()}
    for e in entries:
        row = totals[e["resource_id"]]
        if e["status"] == BookingStatus.CANCELADA.value:
            row["cancelled"] += 1
        elif e["status"] == BookingStatus.NO_SHOW.value:
            row["no_show"] += 1
        elif e["status"] in (BookingStatus.PENDENTE.value, BookingStatus.CONFIRMADA.value):
            row["planned"] += 1
        else:
            row["uses"] += 1
            row["occupied_minutes"] += e["occupied_minutes"]
        row["revenue"] = round(row["revenue"] + e["revenue"], 2)  # a cancelled marcação refunded by NC brings 0
    return {"entries": entries, "summary": list(totals.values())}
