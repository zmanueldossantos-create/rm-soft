"""
Cobrar uma marcação - a spa, a salon, a consulting room: the client of a booked
service pays it at the till, and the marcação is over.

The sale is an ordinary till sale (pos_service.checkout: series, VAT, payments,
session, withholding), with the booked service charged as many times as the
booking lasts (hotel_service._stay_quantity: a 60 min service booked for 90 min
is charged twice). The booking is then CONCLUIDA and linked to its invoice
(Booking.invoice_id). It keeps its slot until its planned end
(booking_service._has_overlap): paid before the service, the practitioner is
still taken.

An activity whose module has the hotel stay (HOTEL_STAY) bills a booking
through its check-in and its account instead: Cobrar is refused there, and the
screen offers it only where there is no check-in.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.invoice import Invoice
from app.models.point_of_sale import PointOfSale
from app.models.service import Service
from app.services.booking_service import get_booking_or_raise
from app.services.document_rules import default_paid_on_issue_type
from app.services.hotel_service import LUANDA, NoDefaultPosError, _stay_quantity
from app.services.pos_service import checkout
from app.services.resource_service import get_resource_or_raise
from app.services.sector_service import activity_has_capability
from app.services.stay_text import stay_observation


class BookingNotChargeableError(Exception):
    """The marcação cannot be charged: not pending/confirmed, no priced service, or a later day."""


async def charge_booking(
    db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID, selling_user: "User", pos_id: uuid.UUID,
    payments: list[dict], customer_id: uuid.UUID | None = None, now: datetime | None = None,
) -> tuple[Booking, Invoice]:
    """Everything is checked before the sale - the state, the service and its price, the day, the till of the
    resource's activity - so nothing is ever cashed for a marcação that cannot end here. customer_id: the customer
    of the invoice, chosen at the till (the screen proposes the booking's own); None is Consumidor final."""
    booking = await get_booking_or_raise(db, company_id, booking_id)
    if booking.status not in (BookingStatus.PENDENTE, BookingStatus.CONFIRMADA):
        raise BookingNotChargeableError("Só uma reserva pendente ou confirmada pode ser cobrada")
    service = None
    if booking.service_id is not None:
        service = (await db.execute(
            select(Service).where(Service.id == booking.service_id, Service.company_id == company_id)
        )).scalar_one_or_none()
    if service is None or service.price is None or float(service.price) <= 0:
        raise BookingNotChargeableError("Esta reserva não tem um serviço com preço - escolha o serviço em Editar")

    moment = now or datetime.now(timezone.utc)
    booked_day = booking.starts_at.astimezone(LUANDA).date()
    if booked_day > moment.astimezone(LUANDA).date():
        raise BookingNotChargeableError(f"Esta reserva é para {booked_day.strftime('%d/%m/%Y')} - cobra-se no próprio dia")

    resource = await get_resource_or_raise(db, company_id, booking.resource_id)
    if await activity_has_capability(db, resource.activity_id, "HOTEL_STAY"):
        raise BookingNotChargeableError("Nesta atividade a reserva fatura-se pelo check-in e pela conta da estadia")
    pos = (await db.execute(
        select(PointOfSale).where(PointOfSale.id == pos_id, PointOfSale.activity_id == resource.activity_id)
    )).scalar_one_or_none()
    if pos is None:
        raise NoDefaultPosError("Este ponto de venda não pertence à atividade do recurso")

    invoice = await checkout(
        db, company_id, pos.id, selling_user, customer_id,
        [{"product_id": None, "service_id": str(service.id),
          "quantity": float(_stay_quantity(service, booking.starts_at, booking.ends_at)), "sale_unit_id": None}],
        payments, invoice_type=await default_paid_on_issue_type(db),
        stay_sale=True,  # the service of a resource that requires one: sold with its booking only
        observations=stay_observation(resource.name, booking.starts_at, booking.ends_at, booking.guest_name,
                                      booking.party_size, person_label="Cliente"),
    )
    booking.status = BookingStatus.CONCLUIDA
    booking.invoice_id = invoice.id
    await db.commit()
    await db.refresh(booking)
    return booking, invoice
