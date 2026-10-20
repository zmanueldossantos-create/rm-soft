"""
The AI assistant on Telegram: the bot's settings (SUPER_ADMIN), the messages read from Telegram - by the application
itself in a local installation (getUpdates, no public address needed), by Telegram's call of the webhook in SaaS - and
the answers sent back (text in Telegram's HTML, PDFs as documents).
"""
import asyncio
import html
import logging
import re
import secrets

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secret_box import decrypt_secret, encrypt_secret
from app.services.platform_settings_service import get_or_create_platform_settings

logger = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"
MAX_TEXT = 4000  # Telegram refuses more than 4 096 characters per message
CHANNEL = "TELEGRAM"


class TelegramError(Exception):
    """Telegram refused or could not be reached - the message is shown as it is (PT-PT)."""


async def call(token: str, method: str, data: dict | None = None, files: dict | None = None, timeout: float = 30) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(API.format(token=token, method=method), data=data if files else None,
                                         json=None if files else data, files=files)
    except httpx.HTTPError:
        raise TelegramError("Sem ligação ao Telegram - verifique a ligação à internet")
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code == 401:
        raise TelegramError("Token do bot recusado pelo Telegram")
    if not body.get("ok"):
        raise TelegramError(f"O Telegram recusou o pedido: {body.get('description', response.status_code)}")
    return body.get("result")


# ---------- The bot's settings (SUPER_ADMIN)

async def bot_token(db: AsyncSession) -> str | None:
    return decrypt_secret((await get_or_create_platform_settings(db)).telegram_bot_token_encrypted)


async def set_bot_token(db: AsyncSession, token: str) -> dict:
    """Checks the token with Telegram (getMe) and keeps it encrypted; "" removes the bot."""
    settings = await get_or_create_platform_settings(db)
    token = (token or "").strip()
    if not token:
        settings.telegram_bot_token_encrypted = settings.telegram_bot_username = None
        await db.commit()
        return {"configured": False, "username": None}
    me = await call(token, "getMe")
    settings.telegram_bot_token_encrypted = encrypt_secret(token)
    settings.telegram_bot_username = me.get("username")
    settings.telegram_webhook_secret = settings.telegram_webhook_secret or secrets.token_urlsafe(24)
    await db.commit()
    return {"configured": True, "username": settings.telegram_bot_username}


# ---------- Telegram's HTML

def to_html(markdown: str) -> str:
    """The panel's little markdown in Telegram's HTML: **bold**, «- » bullets, # titles, | tables | as lines."""
    lines = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            stripped = " · ".join(cells)
        stripped = re.sub(r"^#{1,4}\s+(.*)$", r"**\1**", stripped)
        stripped = re.sub(r"^[-*•]\s+", "• ", stripped)
        lines.append(stripped)
    text = html.escape("\n".join(lines), quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _chunks(text: str) -> list[str]:
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_TEXT and current:
            parts.append(current)
            current = ""
        current += line + "\n"
    return [p for p in parts + [current] if p.strip()]


async def send_items(token: str, chat_id: str, items: list[dict]) -> None:
    for item in items:
        if "text" in item:
            for part in _chunks(to_html(item["text"])):
                await call(token, "sendMessage", {"chat_id": chat_id, "text": part, "parse_mode": "HTML",
                                                  "disable_web_page_preview": True})
        elif "document" in item:
            filename, content, caption = item["document"]
            await call(token, "sendDocument", {"chat_id": chat_id, "caption": caption[:1000]},
                       files={"document": (filename, content, "application/pdf")}, timeout=60)


# ---------- A message from Telegram

async def process_update(update: dict) -> None:
    """One update, in a session of its own: the answer sent back to the same chat. Never raises."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai.channels import handle_incoming
    message = update.get("message") or update.get("edited_message")
    if not message or "chat" not in message:
        return
    chat_id = str(message["chat"]["id"])
    sender = message.get("from") or {}
    name = ("@" + sender["username"]) if sender.get("username") else " ".join(
        p for p in (sender.get("first_name"), sender.get("last_name")) if p) or None
    async with AsyncSessionLocal() as db:
        token = await bot_token(db)
        if not token:
            return
        try:
            await call(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})
            items = await handle_incoming(db, CHANNEL, chat_id, name, message.get("text") or "")
        except Exception:  # the chat always gets an answer, the loop never stops
            logger.exception("Telegram update failed")
            items = [{"text": "Ocorreu um erro ao responder. Tente de novo."}]
        try:
            await send_items(token, chat_id, items)
        except TelegramError:
            logger.exception("Telegram answer not sent")


async def polling_loop() -> None:
    """Local installation: reads the bot's messages itself (long polling), forever - waits while no bot is set."""
    from app.core.database import AsyncSessionLocal
    offset, active_token = None, None
    while True:
        try:
            async with AsyncSessionLocal() as db:
                token = await bot_token(db)
            if not token:
                active_token = None
                await asyncio.sleep(30)
                continue
            if token != active_token:  # a new bot: Telegram only hands its messages to a reader when no webhook is set
                await call(token, "deleteWebhook", {"drop_pending_updates": False})
                active_token, offset = token, None
            updates = await call(token, "getUpdates", {"timeout": 25, **({"offset": offset} if offset else {})}, timeout=35)
            for update in updates or []:
                offset = update["update_id"] + 1
                await process_update(update)
        except asyncio.CancelledError:
            raise
        except TelegramError as e:
            logger.warning("Telegram polling: %s", e)
            await asyncio.sleep(15)
        except Exception:
            logger.exception("Telegram polling stopped for a moment")
            await asyncio.sleep(15)
