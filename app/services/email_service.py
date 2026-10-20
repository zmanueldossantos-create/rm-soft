"""
The company's email account (SMTP) and the sending of an email from it - the company's own address, never RM SOFT's.
The password is kept encrypted and never sent back to a screen. Sending runs in a thread (smtplib is blocking).
"""
import asyncio
import re
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secret_box import decrypt_secret, encrypt_secret, secret_hint
from app.models.company_email_settings import CompanyEmailSettings

SECURITIES = ("STARTTLS", "SSL", "NONE")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailError(Exception):
    """The email could not be configured or sent - the message is shown as it is (PT-PT)."""


def valid_email(address: str | None) -> bool:
    return bool(address and EMAIL_PATTERN.match(address.strip()))


async def _settings(db: AsyncSession, company_id: uuid.UUID) -> CompanyEmailSettings | None:
    return (await db.execute(select(CompanyEmailSettings).where(CompanyEmailSettings.company_id == company_id))).scalar_one_or_none()


def _view(row: CompanyEmailSettings | None) -> dict:
    if row is None:
        return {"configured": False, "smtp_host": "", "smtp_port": 587, "security": "STARTTLS", "username": "",
                "from_email": "", "from_name": "", "has_password": False, "password_hint": None, "is_active": False}
    password = decrypt_secret(row.password_encrypted)
    return {"configured": row.is_active, "smtp_host": row.smtp_host, "smtp_port": row.smtp_port, "security": row.security,
            "username": row.username or "", "from_email": row.from_email, "from_name": row.from_name or "",
            "has_password": bool(row.password_encrypted),
            "password_hint": secret_hint(password) if password else ("Ilegível - introduza de novo" if row.password_encrypted else None),
            "is_active": row.is_active}


async def get_email_settings(db: AsyncSession, company_id: uuid.UUID) -> dict:
    return _view(await _settings(db, company_id))


async def update_email_settings(db: AsyncSession, company_id: uuid.UUID, smtp_host: str, smtp_port: int, security: str,
                                username: str | None, password: str | None, from_email: str, from_name: str | None,
                                is_active: bool = True) -> dict:
    """password: None = unchanged, "" = removed, otherwise the new one."""
    smtp_host, from_email = (smtp_host or "").strip(), (from_email or "").strip()
    if not smtp_host:
        raise EmailError("Indique o servidor de envio (SMTP)")
    if not 0 < int(smtp_port) < 65536:
        raise EmailError("Porta inválida")
    if security not in SECURITIES:
        raise EmailError("Segurança inválida")
    if not valid_email(from_email):
        raise EmailError("Endereço de envio inválido")
    # one sending address, one company: another company could otherwise send documents in its name
    taken = (await db.execute(select(CompanyEmailSettings.id).where(
        func.lower(CompanyEmailSettings.from_email) == from_email.lower(), CompanyEmailSettings.company_id != company_id,
    ))).first()
    if taken:
        raise EmailError("Este endereço de envio já é usado por outra empresa")
    row = await _settings(db, company_id)
    if row is None:
        row = CompanyEmailSettings(company_id=company_id, smtp_host=smtp_host, smtp_port=smtp_port, security=security,
                                   from_email=from_email)
        db.add(row)
    row.smtp_host, row.smtp_port, row.security, row.from_email = smtp_host, int(smtp_port), security, from_email
    row.username = (username or "").strip() or None
    row.from_name = (from_name or "").strip() or None
    row.is_active = is_active
    if password is not None:
        row.password_encrypted = encrypt_secret(password) if password else None
    await db.commit()
    await db.refresh(row)
    return _view(row)


def _deliver(config: dict, message: EmailMessage) -> None:
    """The SMTP conversation itself (blocking, run in a thread) - replaced in the tests."""
    try:
        if config["security"] == "SSL":
            server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=30, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(config["host"], config["port"], timeout=30)
        with server:
            if config["security"] == "STARTTLS":
                server.starttls(context=ssl.create_default_context())
            if config["username"]:
                server.login(config["username"], config["password"] or "")
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise EmailError("O servidor de email recusou o utilizador ou a palavra-passe")
    except smtplib.SMTPRecipientsRefused:
        raise EmailError("O servidor de email recusou o destinatário")
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"Não foi possível enviar o email: {e}"[:300])


async def send_email(db: AsyncSession, company_id: uuid.UUID, to: str, subject: str, body: str,
                     attachments: list[tuple[str, bytes, str]] | None = None) -> None:
    """Sends from the company's account. attachments: [(file name, content, MIME type such as application/pdf)]."""
    row = await _settings(db, company_id)
    if row is None or not row.is_active:
        raise EmailError("O email da empresa não está configurado (Definições da Empresa → Email)")
    if not valid_email(to):
        raise EmailError(f"Endereço de email inválido: {to}")
    message = EmailMessage()
    message["From"] = formataddr((row.from_name or "", row.from_email))
    message["To"] = to.strip()
    message["Subject"] = subject
    message.set_content(body)
    for filename, content, mime in attachments or []:
        maintype, _, subtype = mime.partition("/")
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    config = {"host": row.smtp_host, "port": row.smtp_port, "security": row.security, "username": row.username,
              "password": decrypt_secret(row.password_encrypted)}
    await asyncio.to_thread(_deliver, config, message)


async def send_test_email(db: AsyncSession, company_id: uuid.UUID, to: str) -> None:
    await send_email(db, company_id, to, "RM SOFT - teste de email",
                     "Este email confirma que o envio a partir da conta da empresa está a funcionar.")
