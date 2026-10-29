"""
What the AI assistant may DO, never by itself: it prepares an action (a Fatura, a Pró-forma or an Orçamento to issue, a
document to send by email), the application checks it and shows it, and does it when the user confirms - or at once
when the gestor chose not to confirm (Definições da Empresa → Assistente IA). The document is issued by the usual
invoicing services (stock, periods, series, AGT), in the user's name and within his permissions.

Preparing a document runs the real creation inside a savepoint that is rolled back: the card shows exactly what
would be issued (prices, VAT, exemptions), and every rule refuses there, before the user is asked.
"""
import json
import re
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import current_user_id
from app.models.activity import Activity
from app.models.ai_pending_action import AiPendingAction
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.payment_term import PaymentTerm
from app.models.product import Product
from app.models.service import Service
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE

logger = logging.getLogger(__name__)
LUANDA = ZoneInfo("Africa/Luanda")
ACTION_LIFETIME = timedelta(minutes=30)

DOCUMENT_TYPES = {  # what the assistant may issue, and the permission of each (FR, NC, RC stay on their screens)
    "FATURA": ("FACTURA", "invoices:issue", "Fatura"),
    "PRO_FORMA": ("PRO_FORMA", "invoices:proforma", "Fatura pró-forma"),
    "ORCAMENTO": ("ORCAMENTO", "invoices:quote", "Orçamento"),
}


class ActionError(Exception):
    """The action is refused - the message goes back to the AI (or to the screen), PT-PT."""


@dataclass
class ActionContext:
    """Who asks, from where, and what the gestor chose - the AI never provides any of it. Plain ids, not the User
    object: a refused creation rolls the session back and would expire it."""
    company_id: uuid.UUID
    user_id: uuid.UUID
    permissions: set[str]
    conversation_id: uuid.UUID | None
    confirm_documents: bool
    confirm_sends: bool
    channel: str = "APP"  # APP | TELEGRAM | WHATSAPP
    actions: list[uuid.UUID] = field(default_factory=list)  # prepared during this question
    outbox: list[tuple[str, bytes, str]] = field(default_factory=list)  # files for the chat: (name, content, caption)


def _money(value) -> float:
    return round(float(value or 0), 2)


def _reference(invoice: Invoice) -> str:
    return f"{DOC_CODE_BY_INVOICE_TYPE.get(invoice.invoice_type.value, 'FT')} {invoice.series}/{invoice.number}"


# ---------- Finding what the user names

async def _customer(db: AsyncSession, company_id: uuid.UUID, text: str | None) -> Customer | None:
    """The customer by NIF or name - None for the Consumidor final (nothing given). Several matches: the AI asks."""
    text = " ".join(str(text or "").split())
    if not text or text.lower() in ("consumidor final", "consumidor", "cliente final"):
        return None
    base = select(Customer).where(Customer.company_id == company_id, Customer.is_active.is_(True))
    by_nif = (await db.execute(base.where(Customer.nif == text))).scalars().first()
    if by_nif:
        return by_nif
    found = (await db.execute(base.where(Customer.name.ilike(f"%{text}%")).order_by(Customer.name).limit(6))).scalars().all()
    exact = [c for c in found if c.name.lower() == text.lower()]
    if len(exact) == 1 or len(found) == 1:
        return (exact or found)[0]
    if not found:
        raise ActionError(f"Cliente «{text}» não encontrado - verifique o nome ou o NIF, ou crie-o em Clientes")
    raise ActionError("Vários clientes correspondem: " + "; ".join(f"{c.name} (NIF {c.nif})" for c in found[:5])
                      + " - indique qual")


async def _article(db: AsyncSession, company_id: uuid.UUID, text: str) -> tuple[str, object]:
    """("product" | "service", the article) by code, barcode or name. Several matches: the AI asks."""
    text = " ".join(str(text or "").split())
    if not text:
        raise ActionError("Uma linha sem artigo")
    products = select(Product).where(Product.company_id == company_id, Product.is_active.is_(True),
                                     Product.is_raw_material.is_(False), Product.internal_use_only.is_(False))
    services = select(Service).where(Service.company_id == company_id, Service.is_active.is_(True))
    exact = (await db.execute(products.where(or_(func.upper(Product.code) == text.upper(), Product.barcode == text)))).scalars().first()
    if exact:
        return "product", exact
    exact = (await db.execute(services.where(func.upper(Service.code) == text.upper()))).scalars().first()
    if exact:
        return "service", exact
    found = [("product", p) for p in (await db.execute(products.where(Product.name.ilike(f"%{text}%")).limit(6))).scalars().all()]
    found += [("service", s) for s in (await db.execute(services.where(Service.name.ilike(f"%{text}%")).limit(6))).scalars().all()]
    same_name = [f for f in found if f[1].name.lower() == text.lower()]
    if len(same_name) == 1 or len(found) == 1:
        return (same_name or found)[0]
    if not found:
        raise ActionError(f"Artigo «{text}» não encontrado")
    raise ActionError(f"Vários artigos correspondem a «{text}»: " + "; ".join(f"{a.name} ({a.code})" for _, a in found[:6])
                      + " - indique qual")


async def _activity(db: AsyncSession, company_id: uuid.UUID, text: str | None) -> Activity:
    activities = (await db.execute(select(Activity).where(Activity.company_id == company_id, Activity.is_active.is_(True))
                                   .order_by(Activity.name))).scalars().all()
    if not activities:
        raise ActionError("A empresa não tem nenhuma atividade ativa")
    text = " ".join(str(text or "").split()).lower()
    if text:
        match = [a for a in activities if text in a.name.lower()]
        if len(match) == 1:
            return match[0]
    if len(activities) == 1:
        return activities[0]
    raise ActionError("Em que atividade? " + ", ".join(a.name for a in activities))


# ---------- Issuing a document

async def _issue(db: AsyncSession, company_id: uuid.UUID, payload: dict, commit: bool) -> Invoice:
    """The document created by the usual services - commit=False for the preview (flushed only)."""
    from app.services.invoice_service import create_invoice, create_pro_forma
    lines = [{"product_id": uuid.UUID(l["product_id"]) if l.get("product_id") else None,
              "service_id": uuid.UUID(l["service_id"]) if l.get("service_id") else None,
              "quantity": l["quantity"]} for l in payload["lines"]]
    customer_id = uuid.UUID(payload["customer_id"]) if payload.get("customer_id") else None
    activity_id = uuid.UUID(payload["activity_id"])
    observations = payload.get("observations") or None
    if payload["invoice_type"] == "FACTURA":
        return await create_invoice(
            db, company_id, activity_id, customer_id, invoice_type="FACTURA", lines_input=lines,
            payment_term_id=uuid.UUID(payload["payment_term_id"]) if payload.get("payment_term_id") else None,
            due_date=date.fromisoformat(payload["due_date"]) if payload.get("due_date") else None,
            observations=observations, prescription=payload.get("prescription"), commit=commit,
        )
    return await create_pro_forma(
        db, company_id, activity_id, customer_id, lines, observations=observations, invoice_type=payload["invoice_type"],
        valid_until=date.fromisoformat(payload["valid_until"]) if payload.get("valid_until") else None, commit=commit,
    )


async def _preview(db: AsyncSession, company_id: uuid.UUID, payload: dict) -> dict:
    """Creates the document in a session of its own, reads it, and rolls it back: exactly what would be issued, and
    whatever an invoicing rule does on a refusal (a rollback) never touches the conversation's session."""
    preview_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    try:
        invoice = await _issue(preview_db, company_id, payload, commit=False)
        lines = (await preview_db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
                                  .order_by(InvoiceLine.line_number, InvoiceLine.created_at, InvoiceLine.id))).scalars().all()
        preview = {
            "linhas": [{"artigo": l.product_name_snapshot, "quantidade": float(l.quantity), "preco": _money(l.unit_price),
                        "iva_pct": float(l.vat_rate_snapshot), "total": _money(l.line_total)} for l in lines],
            "sem_iva": _money(invoice.subtotal), "iva": _money(invoice.vat_total), "total": _money(invoice.total),
            "retencao": _money(invoice.retention_total),
            "validade": invoice.valid_until.isoformat() if getattr(invoice, "valid_until", None) else None,
            "vencimento": invoice.due_date.isoformat() if invoice.due_date else None,
        }
    except ActionError:
        raise
    except Exception as e:  # every invoicing rule (stock, period, series, receita...) refuses here, in its own words
        logger.info("AI document preview refused: %s", e)
        raise ActionError(str(e) or "O documento não pode ser emitido")
    finally:
        await preview_db.rollback()
        await preview_db.close()
    return preview


async def preparar_documento(db: AsyncSession, ctx: ActionContext, arguments: dict) -> dict:
    company_id = ctx.company_id
    kind = str(arguments.get("tipo") or "FATURA").upper().replace("-", "_").replace("Ó", "O")
    if kind not in DOCUMENT_TYPES:
        raise ActionError("Só posso emitir Faturas, Pró-formas e Orçamentos - as outras ficam nos seus ecrãs")
    invoice_type, permission, label = DOCUMENT_TYPES[kind]
    if permission not in ctx.permissions:
        raise ActionError(f"Não tem permissão para emitir: {label}")
    raw_lines = arguments.get("linhas") or []
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ActionError("Indique os artigos e as quantidades")
    if len(raw_lines) > 40:
        raise ActionError("Demasiadas linhas - no máximo 40")
    customer = await _customer(db, company_id, arguments.get("cliente"))
    activity = await _activity(db, company_id, arguments.get("atividade"))
    lines = []
    for raw in raw_lines:
        try:
            quantity = float(str(raw.get("quantidade", 1)).replace(",", "."))
        except (TypeError, ValueError, AttributeError):
            raise ActionError("Quantidade inválida")
        if quantity <= 0:
            raise ActionError("A quantidade deve ser maior do que zero")
        what, article = await _article(db, company_id, raw.get("artigo") if isinstance(raw, dict) else raw)
        lines.append({"product_id": str(article.id) if what == "product" else None,
                      "service_id": str(article.id) if what == "service" else None, "quantity": quantity})
    payload = {"invoice_type": invoice_type, "activity_id": str(activity.id),
               "customer_id": str(customer.id) if customer else None, "lines": lines,
               "observations": (str(arguments.get("observacoes") or "").strip() or None)}
    if invoice_type == "FACTURA" and customer is not None and customer.payment_term_id:
        term = await db.get(PaymentTerm, customer.payment_term_id)  # the customer's own term and due date
        if term is not None:
            payload["payment_term_id"] = str(term.id)
            payload["due_date"] = (date.today() + timedelta(days=int(term.days or 0))).isoformat()
    receita = arguments.get("receita")
    if invoice_type == "FACTURA" and isinstance(receita, dict):  # Farmácia: the receita the medicines are dispensed against
        payload["prescription"] = {key: (str(receita.get(src) or "").strip() or None) for key, src in (
            ("number", "numero"), ("prescriber", "medico"), ("health_unit", "unidade_saude"),
            ("patient_name", "utente"), ("patient_document", "documento_utente"))}
    if invoice_type == "ORCAMENTO" and arguments.get("validade"):
        try:
            payload["valid_until"] = date.fromisoformat(str(arguments["validade"])).isoformat()
        except ValueError:
            raise ActionError("Validade inválida - use AAAA-MM-DD")
    preview = await _preview(db, company_id, payload)
    summary = {"titulo": f"{label} para {customer.name if customer else 'Consumidor final'}", "tipo": label,
               "cliente": customer.name if customer else "Consumidor final", "nif": customer.nif if customer else None,
               "atividade": activity.name, **preview}
    if payload.get("prescription", {}).get("number"):
        summary["receita"] = payload["prescription"]["number"]
    return await _propose(db, ctx, "ISSUE_DOCUMENT", payload, summary, ctx.confirm_documents)


# ---------- Sending a document by email

async def enviar_documento_email(db: AsyncSession, ctx: ActionContext, arguments: dict) -> dict:
    from app.services.email_service import get_email_settings, valid_email
    company_id = ctx.company_id
    if not (await get_email_settings(db, company_id))["configured"]:
        raise ActionError("O email da empresa ainda não está configurado (Definições da Empresa → Email)")
    text = " ".join(str(arguments.get("numero") or "").upper().split())
    if "/" not in text:
        raise ActionError("Indique o número completo do documento, por exemplo FT2026/2")
    series, _, number = text.rpartition("/")
    try:
        number = int(number)
    except ValueError:
        raise ActionError("Número de documento inválido")
    invoice = (await db.execute(select(Invoice).where(
        Invoice.company_id == company_id, func.upper(Invoice.series) == series.split(" ")[-1], Invoice.number == number,
    ))).scalars().first()
    if invoice is None:
        raise ActionError(f"Documento {text} não encontrado")
    customer = await db.get(Customer, invoice.customer_id) if invoice.customer_id else None
    to = str(arguments.get("email") or "").strip() or (customer.email if customer else "") or ""
    if not to:
        raise ActionError("O cliente não tem email registado - indique o endereço")
    if not valid_email(to):
        raise ActionError(f"Endereço de email inválido: {to}")
    reference = _reference(invoice)
    message = str(arguments.get("mensagem") or "").strip()
    payload = {"invoice_id": str(invoice.id), "to": to, "subject": f"{reference}",
               "body": (message + "\n\n" if message else "") + f"Segue em anexo o documento {reference}."}
    summary = {"titulo": f"Enviar {reference} por email", "documento": reference, "para": to,
               "cliente": customer.name if customer else "Consumidor final", "total": _money(invoice.total)}
    return await _propose(db, ctx, "SEND_EMAIL", payload, summary, ctx.confirm_sends)


# ---------- Creating a customer

async def criar_cliente(db: AsyncSession, ctx: ActionContext, arguments: dict) -> dict:
    """A new customer, checked as the Clientes screen does (NIF unique in the company), created on confirmation."""
    from app.services.customer_service import CustomerAlreadyExistsError, _check_nif_available
    from app.services.email_service import valid_email
    if "customers:create" not in ctx.permissions:
        raise ActionError("Não tem permissão para criar clientes")
    name = " ".join(str(arguments.get("nome") or "").split())
    nif = re.sub(r"\s", "", str(arguments.get("nif") or "")).upper()
    if len(name) < 2:
        raise ActionError("Indique o nome do cliente")
    if not nif:
        raise ActionError("Indique o NIF do cliente (para um particular sem NIF, use o Consumidor final)")
    if not re.fullmatch(r"[0-9A-Z]{6,20}", nif):
        raise ActionError(f"NIF inválido: {nif}")
    kind = str(arguments.get("tipo") or "").upper()
    if kind not in ("COLETIVA", "SINGULAR"):
        kind = "SINGULAR" if len(nif) == 14 else "COLETIVA"  # a BI number (14) is a person, a 10-digit NIF a company
    email = str(arguments.get("email") or "").strip() or None
    if email and not valid_email(email):
        raise ActionError(f"Email inválido: {email}")
    phone = re.sub(r"[^\d+]", "", str(arguments.get("telefone") or "")) or None
    if phone and not phone.startswith("+"):
        phone = "+244" + phone if len(phone) == 9 else "+" + phone
    try:
        await _check_nif_available(db, ctx.company_id, nif)
    except CustomerAlreadyExistsError as e:
        raise ActionError(f"{e} - use o cliente existente")
    payload = {"name": name, "nif": nif, "legal_person_type": "JURIDICA" if kind == "COLETIVA" else "FISICA",
               "email": email, "phone_number": phone,
               "address": str(arguments.get("morada") or "").strip() or None,
               "city": str(arguments.get("cidade") or "").strip() or None}
    summary = {"titulo": f"Novo cliente: {name}", "nome": name, "nif": nif,
               "tipo": "Pessoa coletiva" if kind == "COLETIVA" else "Pessoa singular",
               "telefone": phone, "email": email, "morada": payload["address"], "cidade": payload["city"]}
    return await _propose(db, ctx, "CREATE_CUSTOMER", payload, summary, ctx.confirm_documents)


# ---------- A document's PDF in the user's own chat (WhatsApp / Telegram)

async def enviar_pdf_no_chat(db: AsyncSession, ctx: ActionContext, arguments: dict) -> dict:
    """The PDF goes to the user himself, in the chat he is writing from - he forwards it if he wants: nothing leaves
    to anybody else, so no confirmation."""
    from app.services.invoice_pdf_service import render_invoice_pdf
    if ctx.channel == "APP":
        raise ActionError("No ecrã, o PDF abre-se em Faturas → o documento → A4")
    text = " ".join(str(arguments.get("numero") or "").upper().split())
    if "/" not in text:
        raise ActionError("Indique o número completo do documento, por exemplo FT2026/2")
    series, _, number = text.rpartition("/")
    try:
        number = int(number)
    except ValueError:
        raise ActionError("Número de documento inválido")
    invoice = (await db.execute(select(Invoice).where(
        Invoice.company_id == ctx.company_id, func.upper(Invoice.series) == series.split(" ")[-1], Invoice.number == number,
    ))).scalars().first()
    if invoice is None:
        raise ActionError(f"Documento {text} não encontrado")
    pdf, filename = await render_invoice_pdf(db, ctx.company_id, invoice.id, "a4")
    ctx.outbox.append((filename, pdf, _reference(invoice)))
    return {"estado": "feito", "nota": f"O PDF de {_reference(invoice)} segue nesta conversa"}


def action_text(action: AiPendingAction) -> str:
    """The card, for a chat: what will be done, then how to answer."""
    s = action.summary or {}

    def kz(value) -> str:
        return f"{float(value or 0):,.2f}".replace(",", " ").replace(".", ",") + " Kz"
    if action.kind == "CREATE_CUSTOMER":
        lines = [f"**{s.get('titulo')}**", f"NIF {s.get('nif')} · {s.get('tipo')}"]
        lines += [v for v in (s.get("telefone"), s.get("email"), ", ".join(x for x in (s.get("morada"), s.get("cidade")) if x)) if v]
    elif action.kind == "ISSUE_DOCUMENT":
        lines = [f"**{s.get('titulo')}**", f"{s.get('cliente')}" + (f" · NIF {s['nif']}" if s.get("nif") else "")
                 + (f" · Receita {s['receita']}" if s.get("receita") else "")]
        lines += [f"- {l['quantidade']:g} × {l['artigo']} — {kz(l['total'])}" for l in s.get("linhas", [])]
        lines.append(f"IVA {kz(s.get('iva'))} · **Total {kz(s.get('total'))}**")
        if s.get("validade"):
            lines.append(f"Válido até {s['validade']}")
    else:
        lines = [f"**{s.get('titulo')}**", f"Para: {s.get('para')}"]
    return "\n".join(lines) + "\n\nResponda **SIM** para confirmar ou **NÃO** para cancelar."


# ---------- Proposing, confirming, cancelling

async def _propose(db: AsyncSession, ctx: ActionContext, kind: str, payload: dict, summary: dict, confirm: bool) -> dict:
    action = AiPendingAction(company_id=ctx.company_id, user_id=ctx.user_id, conversation_id=ctx.conversation_id,
                             kind=kind, payload=payload, summary=summary, status="PENDENTE",
                             expires_at=datetime.now(LUANDA) + ACTION_LIFETIME)
    db.add(action)
    await db.commit()  # kept whatever happens next in the conversation (a later refusal rolls the session back)
    ctx.actions.append(action.id)
    if confirm:
        return {"estado": "a_aguardar_confirmacao", "resumo": summary,
                "nota": "Mostrado ao utilizador com os botões Confirmar / Cancelar (ou responder SIM / NÃO). Nada foi feito ainda."}
    await execute_action(db, action, ctx.user_id)
    return {"estado": "feito" if action.status == "FEITA" else "falhou", "resultado": action.result}


async def execute_action(db: AsyncSession, action: AiPendingAction, user_id: uuid.UUID) -> None:
    """Does the action for real (in the user's name) and records the result - FEITA or FALHOU, never an exception."""
    from app.services.email_service import EmailError, send_email
    from app.services.invoice_pdf_service import render_invoice_pdf
    current_user_id.set(user_id)  # the document records who issued it, whatever the channel
    company_id = action.company_id
    try:
        if action.kind == "ISSUE_DOCUMENT":
            invoice = await _issue(db, company_id, action.payload, commit=True)
            action.result = {"documento": _reference(invoice), "invoice_id": str(invoice.id), "total": _money(invoice.total)}
        elif action.kind == "CREATE_CUSTOMER":
            from app.services.customer_service import create_customer, suggest_next_customer_code
            p = action.payload
            customer = await create_customer(
                db, company_id, p["name"], p["nif"], email=p.get("email"), phone_number=p.get("phone_number"),
                address=p.get("address"), city=p.get("city"), legal_person_type=p["legal_person_type"],
                customer_code=await suggest_next_customer_code(db, company_id))
            action.result = {"cliente": customer.name, "codigo": customer.customer_code, "customer_id": str(customer.id)}
        elif action.kind == "SEND_EMAIL":
            pdf, filename = await render_invoice_pdf(db, company_id, uuid.UUID(action.payload["invoice_id"]), "a4")
            await send_email(db, company_id, action.payload["to"], action.payload["subject"], action.payload["body"],
                             [(filename, pdf, "application/pdf")])
            action.result = {"enviado_para": action.payload["to"]}
        else:
            raise ActionError("Ação desconhecida")
        action.status = "FEITA"
    except (ActionError, EmailError) as e:
        await _failed(db, action, str(e))
        return
    except Exception as e:
        logger.warning("AI action %s failed: %s", action.id, e)
        await _failed(db, action, str(e) or "A ação falhou")
        return
    action.decided_at = datetime.now(LUANDA)
    await db.commit()


async def _failed(db: AsyncSession, action: AiPendingAction, message: str) -> None:
    """A refused creation rolled the session back: the action is written again with its failure."""
    action_id = action.id
    await db.rollback()
    row = await db.get(AiPendingAction, action_id)
    target = row if row is not None else action
    if row is None:
        db.add(action)
    target.status, target.result, target.decided_at = "FALHOU", {"erro": message[:300]}, datetime.now(LUANDA)
    await db.commit()


async def get_action(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, action_id: uuid.UUID) -> AiPendingAction:
    action = (await db.execute(select(AiPendingAction).where(
        AiPendingAction.id == action_id, AiPendingAction.company_id == company_id, AiPendingAction.user_id == user_id,
    ))).scalar_one_or_none()
    if action is None:
        raise ActionError("Ação não encontrada")
    return action


async def decide_action(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, action_id: uuid.UUID,
                        confirm: bool) -> tuple[AiPendingAction, str]:
    """The user's Confirmar / Cancelar (or SIM / NÃO): (the action, the line added to the conversation)."""
    from app.models.ai_conversation import AiMessage
    action = await get_action(db, company_id, user_id, action_id)
    if action.status != "PENDENTE":
        raise ActionError("Esta ação já foi tratada")
    if action.expires_at < datetime.now(LUANDA):
        action.status, action.decided_at = "EXPIRADA", datetime.now(LUANDA)
        await db.commit()
        raise ActionError("Esta ação expirou - peça de novo ao assistente")
    if confirm:
        await execute_action(db, action, user_id)
    else:
        action.status, action.decided_at = "CANCELADA", datetime.now(LUANDA)
        await db.commit()
    await db.refresh(action)
    text = outcome_text(action)
    if action.conversation_id:
        db.add(AiMessage(conversation_id=action.conversation_id, company_id=action.company_id, role="assistant",
                         content=text, created_at=datetime.now(LUANDA)))
        await db.commit()
    return action, text


def outcome_text(action: AiPendingAction) -> str:
    result = action.result or {}
    if action.status == "CANCELADA":
        return "Ação cancelada - nada foi feito."
    if action.status == "FALHOU":
        return f"Não foi possível concluir: {result.get('erro', 'erro desconhecido')}"
    if action.kind == "CREATE_CUSTOMER":
        return f"Cliente **{result.get('cliente')}** criado (código {result.get('codigo')})."
    if action.kind == "ISSUE_DOCUMENT":
        total = f"{result.get('total', 0):,.2f}".replace(",", " ").replace(".", ",")
        return f"**{result.get('documento')}** emitido - {total} Kz."
    return f"Documento enviado por email para {result.get('enviado_para')}."


ACTION_TOOLS = [
    ("preparar_documento", ("invoices:issue", "invoices:proforma", "invoices:quote"), preparar_documento,
     "Prepara uma Fatura (FT, a pagar depois), uma Pró-forma ou um Orçamento: cliente (nome ou NIF; vazio = consumidor "
     "final), artigos com quantidades. A aplicação calcula preços e IVA e mostra o documento ao utilizador, que confirma "
     "(se a empresa o exigir). Fatura/Recibo, notas de crédito e recibos não: esses fazem-se nos seus ecrãs. "
     "Se a ferramenta disser que vários clientes ou artigos correspondem, pergunta ao utilizador qual. "
     "Farmácia: um medicamento sujeito a receita exige a receita no campo «receita» (n.º, e para a receita especial o "
     "utente e o seu documento) - pede esses dados ao utilizador; nunca os ponhas nas observações.",
     {"type": "object", "properties": {
         "tipo": {"type": "string", "enum": ["FATURA", "PRO_FORMA", "ORCAMENTO"]},
         "cliente": {"type": "string", "description": "Nome ou NIF do cliente (vazio = consumidor final)"},
         "linhas": {"type": "array", "items": {"type": "object", "properties": {
             "artigo": {"type": "string", "description": "Nome ou código do produto/serviço"},
             "quantidade": {"type": "number"}}, "required": ["artigo", "quantidade"]}},
         "atividade": {"type": "string", "description": "A atividade, se a empresa tiver várias"},
         "observacoes": {"type": "string"},
         "validade": {"type": "string", "description": "Orçamento: válido até AAAA-MM-DD (30 dias por omissão)"},
         "receita": {"type": "object", "description": "Fatura com medicamentos sujeitos a receita (Farmácia)",
                     "properties": {"numero": {"type": "string"}, "medico": {"type": "string"},
                                    "unidade_saude": {"type": "string"}, "utente": {"type": "string"},
                                    "documento_utente": {"type": "string"}}}},
      "required": ["tipo", "linhas"]}),
    ("enviar_documento_email", ("invoices:view",), enviar_documento_email,
     "Envia um documento (PDF A4) por email, a partir do email da empresa: para o email do cliente ou o endereço indicado. "
     "Confirmado pelo utilizador se a empresa o exigir.",
     {"type": "object", "properties": {
         "numero": {"type": "string", "description": "Ex.: FT2026/3"},
         "email": {"type": "string", "description": "Destinatário (vazio = o email do cliente)"},
         "mensagem": {"type": "string", "description": "Texto curto antes da menção do anexo (opcional)"}},
      "required": ["numero"]}),
    ("criar_cliente", ("customers:create",), criar_cliente,
     "Cria um cliente novo: nome e NIF obrigatórios (o NIF é único na empresa); tipo COLETIVA (empresa) ou SINGULAR "
     "(particular); telefone, email, morada e cidade se o utilizador os der - não inventes nenhum dado. Confirmado pelo "
     "utilizador se a empresa o exigir. Para faturar a seguir a um cliente novo, espera que a criação esteja feita.",
     {"type": "object", "properties": {
         "nome": {"type": "string"}, "nif": {"type": "string"},
         "tipo": {"type": "string", "enum": ["COLETIVA", "SINGULAR"]},
         "telefone": {"type": "string"}, "email": {"type": "string"}, "morada": {"type": "string"},
         "cidade": {"type": "string"}},
      "required": ["nome", "nif"]}),
    ("enviar_pdf_no_chat", ("invoices:view",), enviar_pdf_no_chat,
     "Envia o PDF de um documento ao próprio utilizador, nesta conversa de WhatsApp / Telegram (para ver ou reencaminhar).",
     {"type": "object", "properties": {"numero": {"type": "string", "description": "Ex.: FT2026/3"}}, "required": ["numero"]}),
]


CHAT_ONLY = {"enviar_pdf_no_chat"}  # offered in a WhatsApp / Telegram chat only


def action_tools_for(permissions: set[str], channel: str = "APP") -> list[dict]:
    return [{"name": name, "description": description, "parameters": parameters}
            for name, needed, _, description, parameters in ACTION_TOOLS
            if any(p in permissions for p in needed) and (channel != "APP" or name not in CHAT_ONLY)]


def is_action_tool(name: str) -> bool:
    return any(t[0] == name for t in ACTION_TOOLS)


async def run_action_tool(db: AsyncSession, ctx: ActionContext, name: str, arguments: dict) -> str:
    entry = next(t for t in ACTION_TOOLS if t[0] == name)
    if not any(p in ctx.permissions for p in entry[1]):
        return json.dumps({"erro": "Ferramenta não disponível para este utilizador"}, ensure_ascii=False)
    try:
        result = await entry[2](db, ctx, arguments or {})
    except ActionError as e:
        result = {"erro": str(e)}
    return json.dumps(result, ensure_ascii=False, default=str)
