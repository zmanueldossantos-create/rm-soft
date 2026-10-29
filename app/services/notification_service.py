"""
Notificações: the gestor's own recipients receive, by email or Telegram, the events he switched on for each one
(app/core/notification_events.py) - option NOTIFICACOES of the plans.

notify() only writes the messages in the outbox, inside the caller's transaction (no commit: a sale rolled back sends
nothing, and a sale never waits for a mail server). notification_loop(), started with the server, sends what is due,
3 retries (1 min, 5 min, 30 min) - then ERRO, visible in the history. Works the same on a client's server and in SaaS;
FOR UPDATE SKIP LOCKED: two server processes never send the same message twice.

Telegram: a bot may only write to a person who wrote to it first - the recipient opens once the link shown here
(t.me/<bot>?start=NT...), the bot answers and keeps the chat (link_recipient, called by the bot's message handler).
"""
import asyncio
import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notification_events import CHANNELS, EVENTS
from app.models.company import Company
from app.models.notification import NotificationOutbox, NotificationRecipient, NotificationSettings
from app.services.email_service import valid_email

log = logging.getLogger(__name__)
OPTION = "NOTIFICACOES"
RETRY_MINUTES = (1, 5, 30)  # after the 1st, 2nd, 3rd failure; then ERRO
POLL_SECONDS = 10
_wake = asyncio.Event()


class NotificationError(Exception):
    """A refused setting or recipient - the message is shown as it is (PT-PT)."""


# ------------------------------------------------------------------------------------------------------- settings

async def get_settings_row(db: AsyncSession, company_id: uuid.UUID) -> NotificationSettings:
    row = await db.get(NotificationSettings, company_id)
    if row is None:
        row = NotificationSettings(company_id=company_id, enabled=True, include_gestor_actions=False)
        db.add(row)
        await db.flush()
    return row


async def available_events(db: AsyncSession, company_id: uuid.UUID) -> list[str]:
    """The events this company's sectors have (no hotel events for a bakery)."""
    from app.services.sector_service import get_company_capabilities
    capabilities = await get_company_capabilities(db, company_id)
    return [e.code for e in EVENTS.values() if e.capability is None or e.capability in capabilities]


async def bot_link_base(db: AsyncSession) -> str | None:
    """https://t.me/<bot>?start= - None when no Telegram bot is set on this server (Configurações of the platform)."""
    from app.services.platform_settings_service import get_or_create_platform_settings
    platform = await get_or_create_platform_settings(db)
    if not platform.telegram_bot_username or not platform.telegram_bot_token_encrypted:
        return None
    return f"https://t.me/{platform.telegram_bot_username.lstrip('@')}?start="


def _recipient_view(r: NotificationRecipient, link_base: str | None) -> dict:
    linked = r.channel != "TELEGRAM" or bool(r.address)
    return {
        "id": str(r.id), "name": r.name, "channel": r.channel, "channel_label": CHANNELS.get(r.channel, r.channel),
        "address": r.address if r.channel != "TELEGRAM" else None, "telegram_name": r.telegram_name,
        "linked": linked, "link": (link_base + r.link_code) if (r.channel == "TELEGRAM" and link_base and r.link_code) else None,
        "events": [e for e in r.events if e in EVENTS], "is_active": r.is_active,
    }


async def overview(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """The Notificações tab: settings, the events offered, the recipients, the last messages."""
    settings = await get_settings_row(db, company_id)
    events = await available_events(db, company_id)
    link_base = await bot_link_base(db)
    recipients = (await db.execute(select(NotificationRecipient).where(NotificationRecipient.company_id == company_id)
                                   .order_by(NotificationRecipient.created_at))).scalars().all()
    history = (await db.execute(select(NotificationOutbox).where(NotificationOutbox.company_id == company_id)
                                .order_by(NotificationOutbox.created_at.desc()).limit(50))).scalars().all()
    from app.services.email_service import get_email_settings
    email = await get_email_settings(db, company_id)
    await db.commit()
    return {
        "settings": {"enabled": settings.enabled, "include_gestor_actions": settings.include_gestor_actions,
                     "sale_min_amount": float(settings.sale_min_amount) if settings.sale_min_amount is not None else None},
        "events": [{"code": EVENTS[c].code, "label": EVENTS[c].label, "description": EVENTS[c].description,
                    "by_others": EVENTS[c].by_others} for c in events],
        "channels": {"EMAIL": bool(email.get("is_active") and email.get("smtp_host")), "TELEGRAM": link_base is not None,
                     "WHATSAPP": False},
        "recipients": [_recipient_view(r, link_base) for r in recipients],
        "history": [{"id": str(h.id), "created_at": h.created_at.isoformat() if h.created_at else None,
                     "recipient": h.recipient_name, "channel": h.channel,
                     "event": EVENTS[h.event].label if h.event in EVENTS else "Teste", "subject": h.subject,
                     "status": h.status, "error": h.last_error} for h in history],
    }


async def update_settings(db: AsyncSession, company_id: uuid.UUID, enabled: bool, include_gestor_actions: bool,
                          sale_min_amount: float | None) -> None:
    if sale_min_amount is not None and sale_min_amount < 0:
        raise NotificationError("O montante mínimo não pode ser negativo")
    row = await get_settings_row(db, company_id)
    row.enabled = bool(enabled)
    row.include_gestor_actions = bool(include_gestor_actions)
    row.sale_min_amount = Decimal(str(sale_min_amount)) if sale_min_amount else None
    await db.commit()


# ----------------------------------------------------------------------------------------------------- recipients

def _new_code() -> str:
    return "NT" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


async def _clean(db: AsyncSession, company_id: uuid.UUID, data: dict, current: NotificationRecipient | None) -> dict:
    name = " ".join((data.get("name") or "").split())[:100]
    if not name:
        raise NotificationError("Indique o nome do destinatário")
    channel = current.channel if current else (data.get("channel") or "")
    if channel not in CHANNELS:
        raise NotificationError("Escolha o canal: Email ou Telegram")
    if channel == "WHATSAPP":
        raise NotificationError("As notificações por WhatsApp chegam em breve - use o Email ou o Telegram")
    if channel == "TELEGRAM" and current is None and await bot_link_base(db) is None:
        raise NotificationError("O bot Telegram não está configurado neste servidor - contacte a RM SOFT")
    address = None
    if channel == "EMAIL":
        address = (data.get("address") or "").strip()
        if not valid_email(address):
            raise NotificationError("Endereço de email inválido")
    offered = set(await available_events(db, company_id))
    events = [code for code in dict.fromkeys(data.get("events") or []) if code in offered]
    return {"name": name, "channel": channel, "address": address, "events": events,
            "is_active": bool(data.get("is_active", True))}


async def add_recipient(db: AsyncSession, company_id: uuid.UUID, data: dict) -> dict:
    clean = await _clean(db, company_id, data, None)
    recipient = NotificationRecipient(company_id=company_id, **clean,
                                      link_code=_new_code() if clean["channel"] == "TELEGRAM" else None)
    db.add(recipient)
    await db.commit()
    await db.refresh(recipient)
    return _recipient_view(recipient, await bot_link_base(db))


async def _recipient_or_raise(db: AsyncSession, company_id: uuid.UUID, recipient_id: uuid.UUID) -> NotificationRecipient:
    recipient = await db.get(NotificationRecipient, recipient_id)
    if recipient is None or recipient.company_id != company_id:
        raise LookupError("Destinatário não encontrado")
    return recipient


async def update_recipient(db: AsyncSession, company_id: uuid.UUID, recipient_id: uuid.UUID, data: dict) -> dict:
    recipient = await _recipient_or_raise(db, company_id, recipient_id)
    clean = await _clean(db, company_id, data, recipient)
    recipient.name, recipient.events, recipient.is_active = clean["name"], clean["events"], clean["is_active"]
    if recipient.channel == "EMAIL":
        recipient.address = clean["address"]
    await db.commit()
    await db.refresh(recipient)
    return _recipient_view(recipient, await bot_link_base(db))


async def delete_recipient(db: AsyncSession, company_id: uuid.UUID, recipient_id: uuid.UUID) -> None:
    recipient = await _recipient_or_raise(db, company_id, recipient_id)
    await db.delete(recipient)
    await db.commit()


async def link_recipient(db: AsyncSession, code: str, chat_id: str, name: str | None) -> str:
    """The Telegram chat that opened a recipient's link (the bot's message handler) - the answer sent back."""
    recipient = (await db.execute(select(NotificationRecipient).where(
        NotificationRecipient.link_code == code.upper(), NotificationRecipient.channel == "TELEGRAM"))).scalar_one_or_none()
    if recipient is None:
        return "Ligação inválida. Peça um novo link ao gestor (Definições da Empresa → Notificações)."
    recipient.address = chat_id
    recipient.telegram_name = (name or "")[:150] or None
    company = await db.get(Company, recipient.company_id)
    await db.commit()
    return (f"Ligado: {recipient.name} vai receber aqui as notificações de **{company.short_name or company.name}** "
            "escolhidas pelo gestor.")


# --------------------------------------------------------------------------------------------------------- notify

def _queue(db: AsyncSession, recipient: NotificationRecipient, event: str, subject: str, text: str) -> None:
    db.add(NotificationOutbox(company_id=recipient.company_id, recipient_id=recipient.id, recipient_name=recipient.name,
                              event=event, channel=recipient.channel, address=recipient.address, subject=subject[:200],
                              text=text[:2000], next_attempt_at=datetime.now(timezone.utc)))


async def notify(db: AsyncSession, company_id: uuid.UUID, event: str, text: str, *, actor=None,
                 amount: float | None = None, subject: str | None = None) -> int:
    """Writes the messages of this event for the recipients who receive it - in the caller's transaction (it commits).
    actor: the user who did it (None: nobody, e.g. stock baixo). amount: the sale's total (VENDA's minimum).
    Never raises: a notification never blocks the operation. Returns how many messages were queued."""
    try:
        from app.services.plan_service import has_option
        spec = EVENTS[event]
        if not await has_option(db, company_id, OPTION):
            return 0
        settings = await db.get(NotificationSettings, company_id)
        if settings is not None and not settings.enabled:
            return 0
        include_gestor = settings is not None and settings.include_gestor_actions
        role = getattr(getattr(actor, "role", None), "value", getattr(actor, "role", None))
        if spec.by_others and role in ("GESTOR", "SUPER_ADMIN") and not include_gestor:
            return 0
        if event == "VENDA" and settings is not None and settings.sale_min_amount is not None and amount is not None \
                and Decimal(str(amount)) < settings.sale_min_amount:
            return 0
        recipients = (await db.execute(select(NotificationRecipient).where(
            NotificationRecipient.company_id == company_id, NotificationRecipient.is_active.is_(True),
            NotificationRecipient.address.is_not(None), NotificationRecipient.events.any(event)))).scalars().all()
        company = await db.get(Company, company_id)
        title = subject or f"{spec.label} - {company.short_name or company.name}"
        for recipient in recipients:
            _queue(db, recipient, event, title, text)
        if recipients:
            _wake.set()
        return len(recipients)
    except Exception:  # noqa: BLE001
        log.exception("notification %s not queued", event)
        return 0


async def send_test(db: AsyncSession, company_id: uuid.UUID, recipient_id: uuid.UUID) -> None:
    recipient = await _recipient_or_raise(db, company_id, recipient_id)
    if not recipient.address:
        raise NotificationError("Este destinatário ainda não abriu o link do Telegram")
    company = await db.get(Company, company_id)
    name = company.short_name or company.name
    _queue(db, recipient, "TESTE", f"Teste - {name}",
           f"Teste das notificações de {name}. Se recebeu esta mensagem, {recipient.name} está bem configurado.")
    await db.commit()
    _wake.set()


# ----------------------------------------------------------------------------------------------------------- send

async def _deliver(db: AsyncSession, message: NotificationOutbox) -> None:
    if message.channel == "EMAIL":
        from app.services.email_service import send_email
        await send_email(db, message.company_id, message.address, message.subject, message.text)
    elif message.channel == "TELEGRAM":
        from app.services.ai.telegram import bot_token, call, to_html
        token = await bot_token(db)
        if not token:
            raise NotificationError("O bot Telegram não está configurado neste servidor")
        await call(token, "sendMessage", {"chat_id": message.address, "parse_mode": "HTML",
                                          "text": to_html(f"**{message.subject}**\n{message.text}")})
    else:
        raise NotificationError(f"Canal {message.channel} ainda não disponível")


async def send_due(db: AsyncSession, deliver=None, now: datetime | None = None) -> int:
    """Sends the messages due now (20 at a time); returns how many were tried. deliver: replaced in the tests."""
    deliver = deliver or _deliver
    now = now or datetime.now(timezone.utc)
    rows = (await db.execute(select(NotificationOutbox).where(
        NotificationOutbox.status == "PENDENTE", NotificationOutbox.next_attempt_at <= now)
        .order_by(NotificationOutbox.next_attempt_at).limit(20).with_for_update(skip_locked=True))).scalars().all()
    for message in rows:
        try:
            await deliver(db, message)
        except Exception as e:  # noqa: BLE001 - whatever the channel says, it is written in the history
            message.attempts += 1
            message.last_error = str(e)[:500] or e.__class__.__name__
            if message.attempts > len(RETRY_MINUTES):
                message.status, message.next_attempt_at = "ERRO", None
            else:
                message.next_attempt_at = now + timedelta(minutes=RETRY_MINUTES[message.attempts - 1])
        else:
            message.status, message.sent_at, message.next_attempt_at, message.last_error = "ENVIADA", now, None, None
    await db.commit()
    return len(rows)


async def notification_loop() -> None:
    """Started with the server: every 10 seconds (at once after a new message), what is due."""
    from app.core.database import AsyncSessionLocal
    while True:
        _wake.clear()
        try:
            async with AsyncSessionLocal() as db:
                await send_due(db)
        except Exception:  # noqa: BLE001 - the loop never stops on one failure
            log.exception("notification loop failed")
        try:
            await asyncio.wait_for(_wake.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass


# ------------------------------------------------------------------------------------- the events' messages (N2)
# Called by the operations themselves, before their commit (the message is kept with the operation, or not at all).
# _safe: whatever goes wrong while writing a notification, the operation goes on - its own changes are flushed first
# (their errors stay theirs), the notification's work is done in a savepoint, undone alone if it fails.

import functools  # noqa: E402


def _safe(helper):
    @functools.wraps(helper)
    async def wrapper(db: AsyncSession, *args, **kwargs):
        await db.flush()
        try:
            async with db.begin_nested():
                await helper(db, *args, **kwargs)
        except Exception:  # noqa: BLE001
            log.exception("notification %s not written", helper.__name__)
    return wrapper

LUANDA_TZ = timezone(timedelta(hours=1))  # Africa/Luanda, no summer time


def money(value) -> str:
    """1 234,50 Kz - as on the documents."""
    text = f"{float(value or 0):,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} Kz"


def _qty(value) -> str:
    value = float(value or 0)
    return str(int(value)) if value == int(value) else f"{value:.3f}".rstrip("0").replace(".", ",")


def _day(moment: datetime) -> str:
    return moment.astimezone(LUANDA_TZ).strftime("%d/%m")


def _hour(moment: datetime) -> str:
    return moment.astimezone(LUANDA_TZ).strftime("%H:%M")


async def _user(db: AsyncSession, user_id):
    from app.models.user import User
    return await db.get(User, user_id) if user_id else None


async def _guest(db: AsyncSession, booking) -> str:
    if booking.guest_name:
        return booking.guest_name
    if booking.customer_id:
        from app.models.customer import Customer
        customer = await db.get(Customer, booking.customer_id)
        if customer is not None and not customer.is_final_consumer:
            return customer.name
    return "Hóspede"


def _document(invoice) -> str:
    return f"{invoice.series}/{invoice.number}"


MAX_SALE_LINES = 10  # a long sale keeps its message readable on a phone: the rest is counted


async def _sale_detail(db: AsyncSession, invoice) -> str:
    """The articles of a sale and how it was paid:
        2 × Donut - 2 280,00 Kz
        1 × Café - 1 824,00 Kz
        Pago: Numerário 4 104,00 Kz"""
    from app.models.invoice_line import InvoiceLine
    from app.models.payment import Payment
    from app.models.payment_method_catalog import PaymentMethodCatalog
    lines = (await db.execute(
        select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id).order_by(InvoiceLine.line_number, InvoiceLine.created_at, InvoiceLine.id)
    )).scalars().all()
    rows = []
    for line in lines[:MAX_SALE_LINES]:
        unit = f" {line.unit_code_snapshot}" if line.unit_code_snapshot and line.unit_code_snapshot != "UN" else ""
        rows.append(f"{_qty(line.quantity)}{unit} × {line.product_name_snapshot} - {money(line.line_total)}")
    if len(lines) > MAX_SALE_LINES:
        hidden = len(lines) - MAX_SALE_LINES
        rows.append(f"+ {hidden} artigo{'s' if hidden > 1 else ''}")
    payments = (await db.execute(
        select(PaymentMethodCatalog.name, Payment.amount)
        .join(PaymentMethodCatalog, PaymentMethodCatalog.id == Payment.payment_method_id)
        .where(Payment.invoice_id == invoice.id).order_by(Payment.created_at)
    )).all()
    if payments:
        rows.append("Pago: " + " + ".join(f"{name} {money(amount)}" for name, amount in payments))
    return "\n".join(rows)


@_safe
async def notify_sale(db: AsyncSession, user, invoice, pos_id) -> None:
    """VENDA: a sale made at a till (Caixa) - not the closing of a table or a stay (their own events)."""
    from app.models.point_of_sale import PointOfSale
    pos = await db.get(PointOfSale, pos_id)
    detail = await _sale_detail(db, invoice)
    await notify(db, invoice.company_id, "VENDA",
                 f"Venda {_document(invoice)} - {money(invoice.total)}\n{detail}\n"
                 f"Caixa: {pos.name if pos else '-'} · Vendedor: {user.full_name}",
                 actor=user, amount=float(invoice.total))


@_safe
async def notify_table_opened(db: AsyncSession, account) -> None:
    from app.models.activity import Activity
    user = await _user(db, account.opened_by_user_id)
    activity = await db.get(Activity, account.activity_id)
    await notify(db, account.company_id, "MESA_ABERTA",
                 f"{account.label} aberta por {user.full_name if user else '-'}" + (f" - {activity.name}" if activity else ""),
                 actor=user)


@_safe
async def notify_table_closed(db: AsyncSession, account, invoice, user) -> None:
    """MESA_FECHADA - or CHECK_OUT when the account is a hotel stay paid at the till."""
    if account.booking_id is not None:
        from app.models.booking import Booking
        booking = await db.get(Booking, account.booking_id)
        guest = await _guest(db, booking) if booking else "Hóspede"
        await notify(db, account.company_id, "CHECK_OUT",
                     f"{account.label} libertado - {guest}\nTotal {money(invoice.total)} ({_document(invoice)})\n"
                     f"{await _sale_detail(db, invoice)}\n{user.full_name}", actor=user)
        return
    await notify(db, account.company_id, "MESA_FECHADA",
                 f"{account.label} fechada - {money(invoice.total)} ({_document(invoice)})\n"
                 f"{await _sale_detail(db, invoice)}\n{user.full_name}", actor=user)


@_safe
async def notify_check_in(db: AsyncSession, booking, resource_name: str, user, walk_in_service: str | None = None) -> None:
    guest = await _guest(db, booking)
    if walk_in_service:
        detail = f"{walk_in_service}, até às {_hour(booking.ends_at)}"
    else:
        nights = max(1, (booking.ends_at.astimezone(LUANDA_TZ).date() - booking.starts_at.astimezone(LUANDA_TZ).date()).days)
        detail = f"{nights} noite{'s' if nights > 1 else ''}, até {_day(booking.ends_at)}"
    await notify(db, booking.company_id, "CHECK_IN", f"{resource_name} ocupado - {guest}\n{detail} · {user.full_name}",
                 actor=user)


@_safe
async def notify_check_out(db: AsyncSession, booking, resource_name: str, user) -> None:
    """A check-out with nothing left to pay (the one paid at the till comes from notify_table_closed)."""
    guest = await _guest(db, booking)
    await notify(db, booking.company_id, "CHECK_OUT",
                 f"{resource_name} libertado - {guest}" + (f"\n{user.full_name}" if user else ""), actor=user)


@_safe
async def notify_online_booking(db: AsyncSession, booking, key_name: str) -> None:
    """A booking arrived from the web site (public API): to confirm at the reception. Nobody «did» it: always sent."""
    from app.models.resource import Resource
    resource = await db.get(Resource, booking.resource_id)
    guest = await _guest(db, booking)
    if booking.party_size:
        guest += f" ({booking.party_size} pax)"
    reference = f" · ref. {booking.external_reference}" if booking.external_reference else ""
    await notify(db, booking.company_id, "RESERVA_ONLINE",
                 f"{resource.name if resource else 'Reserva'} - {guest}\n{_day(booking.starts_at)} {_hour(booking.starts_at)}"
                 f" a {_day(booking.ends_at)} {_hour(booking.ends_at)}\n{key_name}{reference} · a confirmar na receção")


@_safe
async def notify_till_closed(db: AsyncSession, session, user) -> None:
    from app.models.point_of_sale import PointOfSale
    pos = await db.get(PointOfSale, session.pos_id)
    difference = float(session.closing_difference or 0)
    text = (f"{pos.name if pos else 'Caixa'} fechada por {user.full_name if user else '-'}\n"
            f"Esperado {money(session.closing_amount_expected)} · contado {money(session.closing_amount_counted)}")
    text += f"\nDiferença {'+' if difference > 0 else ''}{money(difference)}" if difference else "\nSem diferença"
    if session.closing_notes and difference:
        text += f" - {session.closing_notes}"
    await notify(db, session.company_id, "CAIXA_FECHADA", text, actor=user)


@_safe
async def notify_low_stock(db: AsyncSession, company_id, product, warehouse, before: float, after: float) -> None:
    """STOCK_BAIXO: once, when a sale takes the product to its minimum or under it (not at every following sale)."""
    minimum = float(product.min_stock_threshold or 0)
    if minimum <= 0 or not (before > minimum >= after):
        return
    unit = "UN"
    if product.unit_of_measure_id:
        from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
        row = await db.get(UnitOfMeasureCatalog, product.unit_of_measure_id)
        unit = row.code if row else unit
    await notify(db, company_id, "STOCK_BAIXO",
                 f"{product.name}: {_qty(after)} {unit} (mínimo {_qty(minimum)})" + (f" - {warehouse.name}" if warehouse else ""))
