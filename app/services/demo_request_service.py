"""
«Pedir demonstração» (the public site): a request is kept for the SUPER_ADMIN («Pedidos»), never trusted blindly.

Anti-spam without any outside service:
  - a hidden field («fax») a person never sees (read-only: the browser's autofill never fills it): filled, the request
    is kept but already DESCARTADO with a note - a real person is never lost, a robot never shows among the new ones;
  - a form sent faster than a person can type (MIN_FILL_SECONDS) is refused;
  - at most MAX_PER_HOUR requests from one address in an hour.
The messages come in the visitor's language (pt / en): the site is bilingual.
"""
import uuid
from datetime import datetime, timedelta, timezone

import phonenumbers
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import SECTORS_BY_CODE
from app.models.demo_request import DEMO_DEPLOYMENTS, DEMO_STATUSES, DemoRequest
from app.models.plan import Plan
from app.services.email_service import valid_email

MIN_FILL_SECONDS = 3
MAX_PER_HOUR = 5

MESSAGES = {
    "name": ("Indique o seu nome", "Please enter your name"),
    "company": ("Indique o nome da empresa", "Please enter your company name"),
    "phone": ("Telefone inválido - número internacional, ex.: +244923000000",
              "Invalid phone - international number, e.g. +244923000000"),
    "email": ("Email inválido", "Invalid email"),
    "too_fast": ("O formulário foi enviado depressa demais. Verifique os dados e envie de novo.",
                 "The form was sent too fast. Check your details and send it again."),
    "too_many": ("Recebemos vários pedidos deste endereço. Tente de novo dentro de uma hora, ou fale connosco no WhatsApp.",
                 "We received several requests from this address. Try again in an hour, or talk to us on WhatsApp."),
}


class DemoRequestError(Exception):
    """A request refused - the message is in the visitor's language. too_many: answered 429."""

    def __init__(self, message: str, too_many: bool = False):
        super().__init__(message)
        self.too_many = too_many


def _say(key: str, language: str) -> str:
    pt, en = MESSAGES[key]
    return en if language == "en" else pt


def _phone(value: str) -> str | None:
    """The number in its international form (+244923000000): a local Angolan number is accepted as such."""
    try:
        parsed = phonenumbers.parse((value or "").strip(), "AO")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


ROBOT_NOTE = "Descartado automaticamente: o campo oculto do formulário foi preenchido (provável robô)."


async def create_demo_request(db: AsyncSession, data: dict, ip: str | None) -> DemoRequest:
    """The request kept (a robot's too: already DESCARTADO, see ROBOT_NOTE) - DemoRequestError when refused."""
    language = "en" if data.get("language") == "en" else "pt"
    robot = bool((data.get("fax") or "").strip())
    if float(data.get("elapsed_ms") or 0) < MIN_FILL_SECONDS * 1000:
        raise DemoRequestError(_say("too_fast", language))

    name = " ".join((data.get("name") or "").split())[:120]
    company = " ".join((data.get("company_name") or "").split())[:160]
    if len(name) < 2:
        raise DemoRequestError(_say("name", language))
    if len(company) < 2:
        raise DemoRequestError(_say("company", language))
    phone = _phone(data.get("phone"))
    if phone is None:
        raise DemoRequestError(_say("phone", language))
    email = (data.get("email") or "").strip() or None
    if email and not valid_email(email):
        raise DemoRequestError(_say("email", language))

    if ip:
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = (await db.execute(select(func.count(DemoRequest.id)).where(
            DemoRequest.ip == ip, DemoRequest.created_at >= since))).scalar()
        if recent >= MAX_PER_HOUR:
            raise DemoRequestError(_say("too_many", language), too_many=True)

    plan_id = data.get("plan_id")
    if plan_id is not None:  # only a plan on sale; anything else is simply not kept
        plan_id = (await db.execute(select(Plan.id).where(Plan.id == plan_id, Plan.is_active.is_(True)))).scalar_one_or_none()
    sectors = [code for code in dict.fromkeys(data.get("sectors") or []) if code in SECTORS_BY_CODE][:12]
    deployment = data.get("deployment") if data.get("deployment") in DEMO_DEPLOYMENTS else "NAO_SEI"
    nif = "".join(ch for ch in (data.get("nif") or "") if ch.isalnum()).upper()[:20] or None
    message = (data.get("message") or "").strip()[:1000] or None

    request = DemoRequest(name=name, company_name=company, phone=phone, email=email, nif=nif, sectors=sectors,
                          plan_id=plan_id, deployment=deployment, message=message, language=language, ip=ip,
                          status="DESCARTADO" if robot else "NOVO", notes=ROBOT_NOTE if robot else None)
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request


def view(request: DemoRequest) -> dict:
    return {
        "id": str(request.id), "created_at": request.created_at.isoformat() if request.created_at else None,
        "name": request.name, "company_name": request.company_name, "phone": request.phone, "email": request.email,
        "nif": request.nif,
        "sectors": [{"code": code, "name": SECTORS_BY_CODE[code].name} for code in request.sectors if code in SECTORS_BY_CODE],
        "plan": request.plan.name if request.plan else None,
        "deployment": request.deployment, "deployment_label": DEMO_DEPLOYMENTS.get(request.deployment, request.deployment),
        "message": request.message, "language": request.language,
        "status": request.status, "status_label": DEMO_STATUSES.get(request.status, request.status),
        "notes": request.notes,
        "handled_by": request.handled_by.full_name if request.handled_by else None,
        "handled_at": request.handled_at.isoformat() if request.handled_at else None,
    }


async def list_demo_requests(db: AsyncSession, status: str | None = None) -> list[dict]:
    query = select(DemoRequest).order_by(DemoRequest.created_at.desc())
    if status:
        query = query.where(DemoRequest.status == status)
    return [view(r) for r in (await db.execute(query.limit(500))).scalars().all()]


async def demo_requests_summary(db: AsyncSession) -> dict:
    counts = dict((await db.execute(select(DemoRequest.status, func.count(DemoRequest.id)).group_by(DemoRequest.status))).all())
    return {code: counts.get(code, 0) for code in DEMO_STATUSES}


async def update_demo_request(db: AsyncSession, request_id: uuid.UUID, status: str, notes: str | None, user_id) -> dict:
    request = await db.get(DemoRequest, request_id)
    if request is None:
        raise LookupError("Pedido não encontrado")
    if status not in DEMO_STATUSES:
        raise ValueError("Estado inválido")
    if status != request.status:
        request.status = status
        request.handled_by_user_id = user_id
        request.handled_at = datetime.now(timezone.utc)
    request.notes = (notes or "").strip()[:2000] or None
    await db.commit()
    await db.refresh(request)
    return view(request)
