"""
The AI assistant on WhatsApp (WhatsApp Cloud API, Meta): the RM SOFT number's settings (SUPER_ADMIN), Meta's webhook
(the verification, the signature of every call, the messages) and the answers sent back - text in WhatsApp's own
formatting, PDFs uploaded then sent as documents. The conversation itself is app.services.ai.channels, shared with
Telegram. Meta reaches the webhook only at a public address: SaaS, or a tunnel to test a local installation.
"""
import hashlib
import hmac
import logging
import re
import secrets

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secret_box import decrypt_secret, encrypt_secret, secret_hint
from app.services.platform_settings_service import get_or_create_platform_settings

logger = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v21.0"  # Meta's Graph API version - follow Meta's changes
MAX_TEXT = 4000
CHANNEL = "WHATSAPP"


class WhatsAppError(Exception):
    """Meta refused or could not be reached - the message is shown as it is (PT-PT)."""


# ---------- The number's settings (SUPER_ADMIN)

def settings_view(settings) -> dict:
    token = decrypt_secret(settings.whatsapp_access_token_encrypted)
    return {
        "configured": bool(settings.whatsapp_phone_number_id and settings.whatsapp_access_token_encrypted
                           and settings.whatsapp_app_secret_encrypted),
        "phone_number_id": settings.whatsapp_phone_number_id, "display_number": settings.whatsapp_display_number,
        "has_access_token": bool(settings.whatsapp_access_token_encrypted),
        "access_token_hint": secret_hint(token) if token else None,
        "has_app_secret": bool(settings.whatsapp_app_secret_encrypted),
        "verify_token": settings.whatsapp_verify_token,
        "webhook_path": "/api/v1/channels/whatsapp/webhook",
    }


async def get_settings_view(db: AsyncSession) -> dict:
    return settings_view(await get_or_create_platform_settings(db))


async def update_settings(db: AsyncSession, phone_number_id: str | None, display_number: str | None,
                          access_token: str | None, app_secret: str | None) -> dict:
    """access_token / app_secret: None = unchanged, "" = removed. The verify token is made once, for Meta."""
    settings = await get_or_create_platform_settings(db)
    phone_number_id = re.sub(r"\D", "", phone_number_id or "") or None
    display = re.sub(r"[^\d+]", "", display_number or "") or None
    if display and not display.startswith("+"):
        display = "+" + display
    settings.whatsapp_phone_number_id, settings.whatsapp_display_number = phone_number_id, display
    if access_token is not None:
        settings.whatsapp_access_token_encrypted = encrypt_secret(access_token.strip()) if access_token.strip() else None
    if app_secret is not None:
        settings.whatsapp_app_secret_encrypted = encrypt_secret(app_secret.strip()) if app_secret.strip() else None
    settings.whatsapp_verify_token = settings.whatsapp_verify_token or secrets.token_urlsafe(24)
    await db.commit()
    await db.refresh(settings)
    return settings_view(settings)


# ---------- Meta's webhook

def verify_subscription(settings, mode: str | None, token: str | None, challenge: str | None) -> str | None:
    """Meta's GET when the webhook is registered: the challenge back when our verify token is given, else None."""
    if mode == "subscribe" and token and settings.whatsapp_verify_token and hmac.compare_digest(token, settings.whatsapp_verify_token):
        return challenge or ""
    return None


def signature_valid(settings, body: bytes, header: str | None) -> bool:
    """Every call of Meta is signed with the app secret (X-Hub-Signature-256: sha256=...)."""
    secret = decrypt_secret(settings.whatsapp_app_secret_encrypted)
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def incoming_messages(payload: dict) -> list[dict]:
    """[{from, name, text}] in a webhook call - the statuses (sent, read...) and the other kinds are left out; a
    message that is not text is given text None (answered that only text is read)."""
    out = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
            for message in value.get("messages") or []:
                sender = message.get("from")
                if not sender:
                    continue
                text = (message.get("text") or {}).get("body") if message.get("type") == "text" else None
                out.append({"from": sender, "name": names.get(sender), "text": text})
    return out


# ---------- WhatsApp's formatting and sending

def to_whatsapp(markdown: str) -> str:
    """The panel's little markdown in WhatsApp's: *bold*, «• » bullets, # titles in bold, | tables | as lines."""
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
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", "\n".join(lines))


async def call(token: str, path: str, json: dict | None = None, files: dict | None = None, data: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{GRAPH}/{path}", headers={"Authorization": f"Bearer {token}"},
                                         json=json, files=files, data=data)
    except httpx.HTTPError:
        raise WhatsAppError("Sem ligação ao WhatsApp - verifique a ligação à internet")
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code >= 400:
        error = body.get("error") or {}
        raise WhatsAppError(f"O WhatsApp recusou o pedido: {error.get('message', response.status_code)}")
    return body


def _chunks(text: str) -> list[str]:
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_TEXT and current:
            parts.append(current)
            current = ""
        current += line + "\n"
    return [p.rstrip("\n") for p in parts + [current] if p.strip()]


async def send_items(token: str, phone_number_id: str, to: str, items: list[dict]) -> None:
    for item in items:
        if "text" in item:
            for part in _chunks(to_whatsapp(item["text"])):
                await call(token, f"{phone_number_id}/messages", json={
                    "messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": part}})
        elif "document" in item:
            filename, content, caption = item["document"]
            media = await call(token, f"{phone_number_id}/media", data={"messaging_product": "whatsapp", "type": "application/pdf"},
                               files={"file": (filename, content, "application/pdf")})
            await call(token, f"{phone_number_id}/messages", json={
                "messaging_product": "whatsapp", "to": to, "type": "document",
                "document": {"id": media.get("id"), "filename": filename, "caption": caption[:1000]}})


async def process_message(message: dict) -> None:
    """One message, in a session of its own: the answer sent back to the same number. Never raises."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai.channels import handle_incoming
    async with AsyncSessionLocal() as db:
        settings = await get_or_create_platform_settings(db)
        token, phone_number_id = decrypt_secret(settings.whatsapp_access_token_encrypted), settings.whatsapp_phone_number_id
        if not token or not phone_number_id:
            return
        if message.get("text") is None:
            items = [{"text": "Só sei ler mensagens de texto."}]
        else:
            try:
                items = await handle_incoming(db, CHANNEL, message["from"], message.get("name"), message["text"])
            except Exception:
                logger.exception("WhatsApp message failed")
                items = [{"text": "Ocorreu um erro ao responder. Tente de novo."}]
        try:
            await send_items(token, phone_number_id, message["from"], items)
        except WhatsAppError:
            logger.exception("WhatsApp answer not sent")
