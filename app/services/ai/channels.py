"""
The AI assistant from a chat (Telegram now, WhatsApp next), whatever the channel: linking the chat to a user's account
(a 6-digit code shown in the application, sent from the phone - which proves the phone is his and settles a number
present in several companies), then each message answered by the same assistant as the application's panel - same
tools, same permissions, same monthly count, the actions confirmed by SIM / NÃO.

handle_incoming returns what to send back, channel-neutral: [{"text": markdown}] and [{"document": (name, bytes,
caption)}]; the channel module turns them into its own messages.
"""
import re
import secrets
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_channel import AiChannelLink, AiLinkCode
from app.models.ai_pending_action import AiPendingAction
from app.models.company import Company
from app.models.company_ai_settings import CompanyAiSettings
from app.models.user import User

LUANDA = ZoneInfo("Africa/Luanda")
CHANNELS = {"TELEGRAM": "telegram_enabled", "WHATSAPP": "whatsapp_enabled"}
CODE_LIFETIME = timedelta(minutes=10)
LINK_PATTERN = re.compile(r"^(?:/start\s+|ligar\s+)?(\d{6})$", re.IGNORECASE)
NOT_LINKED = ("Este contacto não está ligado a nenhuma conta RM SOFT. Na aplicação: Definições da Empresa → "
              "Assistente IA → Ligar, e envie aqui o código mostrado.")


class ChannelError(Exception):
    """A linking refused - the message is shown as it is (PT-PT)."""


async def _channel_enabled(db: AsyncSession, company_id: uuid.UUID, channel: str) -> bool:
    settings = (await db.execute(select(CompanyAiSettings).where(CompanyAiSettings.company_id == company_id))).scalar_one_or_none()
    return bool(settings and settings.ai_enabled and getattr(settings, CHANNELS[channel]))


# ---------- Linking (from the application)

async def create_link_code(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, channel: str) -> dict:
    """A new 6-digit code for this user and channel (the previous ones no longer work)."""
    if channel not in CHANNELS:
        raise ChannelError("Canal desconhecido")
    if not await _channel_enabled(db, company_id, channel):
        raise ChannelError(f"O assistente no {channel.title()} não está ativo para a sua empresa")
    now = datetime.now(LUANDA)
    await db.execute(update(AiLinkCode).where(AiLinkCode.user_id == user_id, AiLinkCode.channel == channel,
                                              AiLinkCode.used_at.is_(None)).values(used_at=now))
    code = f"{secrets.randbelow(1_000_000):06d}"
    row = AiLinkCode(company_id=company_id, user_id=user_id, channel=channel, code=code, expires_at=now + CODE_LIFETIME)
    db.add(row)
    await db.commit()
    return {"code": code, "expires_at": row.expires_at}


async def list_links(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    """{channel: {enabled, linked, name, linked_at}} for the user's settings tab."""
    links = {l.channel: l for l in (await db.execute(select(AiChannelLink).where(
        AiChannelLink.user_id == user_id, AiChannelLink.company_id == company_id, AiChannelLink.is_active.is_(True),
    ))).scalars().all()}
    out = {}
    for channel in CHANNELS:
        link = links.get(channel)
        out[channel] = {"enabled": await _channel_enabled(db, company_id, channel), "linked": link is not None,
                        "name": link.external_name if link else None, "linked_at": link.linked_at if link else None}
    return out


async def unlink(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, channel: str) -> None:
    """Desligar: the chat no longer reaches the account (the link is switched off, not deleted)."""
    await db.execute(update(AiChannelLink).where(
        AiChannelLink.user_id == user_id, AiChannelLink.company_id == company_id, AiChannelLink.channel == channel,
    ).values(is_active=False))
    await db.commit()


async def _link(db: AsyncSession, channel: str, external_id: str, external_name: str | None, code: str) -> str:
    now = datetime.now(LUANDA)
    row = (await db.execute(select(AiLinkCode).where(
        AiLinkCode.code == code, AiLinkCode.channel == channel, AiLinkCode.used_at.is_(None), AiLinkCode.expires_at > now,
    ))).scalars().first()
    if row is None:
        return "Código inválido ou expirado. Gere um novo na aplicação (Definições da Empresa → Assistente IA)."
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active or not await _channel_enabled(db, row.company_id, channel):
        return "Não foi possível ligar: a conta ou o assistente não estão ativos."
    # one chat, one account; one account, one chat per channel
    await db.execute(update(AiChannelLink).where(AiChannelLink.channel == channel, AiChannelLink.is_active.is_(True),
                                                 (AiChannelLink.external_id == external_id) | (AiChannelLink.user_id == user.id))
                     .values(is_active=False))
    db.add(AiChannelLink(company_id=row.company_id, user_id=user.id, channel=channel, external_id=external_id,
                         external_name=(external_name or "")[:150] or None))
    row.used_at = now
    company = await db.get(Company, row.company_id)
    name = user.full_name
    await db.commit()
    return (f"Ligado à conta de **{name}** ({company.name}). Pode escrever as suas perguntas aqui - por exemplo "
            "«Quanto vendi hoje?». Escreva **NOVA** para começar outra conversa.")


# ---------- A message from the chat

async def handle_incoming(db: AsyncSession, channel: str, external_id: str, external_name: str | None,
                          text: str) -> list[dict]:
    """The answer to one message of a chat: what to send back (texts in the little markdown of the panel, files)."""
    from app.services.ai.actions import action_text
    from app.services.ai.assistant_service import AssistantError, ConversationNotFoundError, ask
    from app.services.permission_service import has_permission

    text = (text or "").strip()
    if not text:
        return [{"text": "Só sei ler mensagens de texto."}]
    match = LINK_PATTERN.match(text)
    if match:
        return [{"text": await _link(db, channel, external_id, external_name, match.group(1))}]
    link = (await db.execute(select(AiChannelLink).where(
        AiChannelLink.channel == channel, AiChannelLink.external_id == external_id, AiChannelLink.is_active.is_(True),
    ))).scalars().first()
    if link is None:
        return [{"text": NOT_LINKED}]
    link_id, company_id, conversation_id = link.id, link.company_id, link.conversation_id
    user = await db.get(User, link.user_id)
    if user is None or not user.is_active:
        return [{"text": NOT_LINKED}]
    if not await _channel_enabled(db, company_id, channel):
        return [{"text": f"O assistente no {channel.title()} está desativado para a sua empresa."}]
    if not await has_permission(db, company_id, user.role.value, "assistant:use"):
        return [{"text": "A sua conta já não tem acesso ao assistente."}]
    if text.lower() in ("nova", "/nova", "/start", "novo"):
        link.conversation_id = None
        await db.commit()
        return [{"text": "Nova conversa. Em que posso ajudar?"}]

    try:
        try:
            conversation, message = await ask(db, user, text, conversation_id, channel=channel)
        except ConversationNotFoundError:
            conversation, message = await ask(db, user, text, None, channel=channel)
    except AssistantError as e:
        return [{"text": str(e)}]
    outbox = getattr(message, "outbox", []) or []
    out = [{"text": message.content}]
    if message.action_id:
        action = await db.get(AiPendingAction, message.action_id)
        if action is not None and action.status == "PENDENTE":
            out.append({"text": action_text(action)})
    out += [{"document": item} for item in outbox]
    link = await db.get(AiChannelLink, link_id)
    if link is not None and link.conversation_id != conversation.id:
        link.conversation_id = conversation.id
        await db.commit()
    return out
