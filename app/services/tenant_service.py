"""
SaaS mode: which company an address belongs to. Every company has its own subdomain (farmacia-da-luz.rmsystem.co.ao);
the platform has the admin one (admin.rmsystem.co.ao). The login on a company's address only knows that company's
users, and a session opened there is refused on any other address - two companies may have the same phone number
without any confusion. In local mode (one company per installation) none of this applies.

The address is read from X-Tenant-Host (the screen's own address - in development the screens and the backend have
different addresses), else X-Forwarded-Host (the reverse proxy), else Host. It only says which company's login to
show: the password is checked as always.
"""
import re
import unicodedata
import uuid
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.company import Company

RESERVED = {"admin", "www", "api", "app", "mail", "static", "suporte", "support"}
SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class TenantError(Exception):
    """A subdomain refused - the message is shown as it is (PT-PT)."""


@dataclass
class Tenant:
    kind: str  # "admin" | "company" | "none" (no company address: the bare domain, an IP...)
    label: str | None = None  # the subdomain read from the address
    company: Company | None = None  # kind "company": None when no company has this subdomain


def slugify(text: str) -> str:
    """A name turned into a subdomain: no accents, lower case, words joined by '-' (Farmácia da Luz -> farmacia-da-luz)."""
    text = unicodedata.normalize("NFD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-")


def validate_subdomain(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        raise TenantError("Indique o subdomínio da empresa")
    if not SUBDOMAIN_RE.match(value):
        raise TenantError("Subdomínio inválido - use só letras minúsculas, números e «-» (ex.: farmacia-da-luz)")
    if value in RESERVED or value == get_settings().ADMIN_SUBDOMAIN:
        raise TenantError(f"O subdomínio «{value}» está reservado - escolha outro")
    return value


async def ensure_subdomain_available(db: AsyncSession, value: str, company_id: uuid.UUID | None = None) -> str:
    value = validate_subdomain(value)
    owner = (await db.execute(select(Company.id).where(Company.subdomain == value))).scalar_one_or_none()
    if owner is not None and owner != company_id:
        raise TenantError(f"O subdomínio «{value}» já é usado por outra empresa")
    return value


async def suggest_subdomain(db: AsyncSession, name: str) -> str:
    """A free subdomain made from a name: farmacia-da-luz, else farmacia-da-luz-2, -3..."""
    base = slugify(name) or "empresa"
    if base in RESERVED:
        base = f"{base}-empresa"
    taken = set((await db.execute(select(Company.subdomain).where(Company.subdomain.like(base + "%")))).scalars().all())
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def request_host(request: Request) -> str:
    host = request.headers.get("x-tenant-host") or request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return host.split(",")[0].strip().lower().split(":")[0]


def parse_host(host: str) -> tuple[str, str | None]:
    """(kind, subdomain) of an address: on BASE_DOMAIN, or on localhost for development."""
    settings = get_settings()
    for base in (settings.BASE_DOMAIN.lower(), "localhost"):
        if host.endswith("." + base):
            label = host[: -len(base) - 1]
            if not label or "." in label:
                return "none", None
            return ("admin", None) if label == settings.ADMIN_SUBDOMAIN else ("company", label)
    return "none", None


async def resolve_tenant(db: AsyncSession, host: str) -> Tenant:
    kind, label = parse_host(host)
    if kind != "company":
        return Tenant(kind)
    company = (await db.execute(select(Company).where(Company.subdomain == label))).scalar_one_or_none()
    return Tenant("company", label, company)


def tenant_claim(tenant: Tenant) -> str | None:
    """What a session opened on this address carries: the subdomain, or the admin one."""
    if tenant.kind == "admin":
        return get_settings().ADMIN_SUBDOMAIN
    return tenant.label if tenant.kind == "company" else None


def host_claim(host: str) -> str | None:
    """The same, read from the address alone (no database): what a session must carry to be used here."""
    kind, label = parse_host(host)
    return get_settings().ADMIN_SUBDOMAIN if kind == "admin" else label


async def domain_allowed(db: AsyncSession, domain: str) -> bool:
    """For the HTTPS proxy (Caddy, on-demand certificates): only the admin address and active companies' ones."""
    domain = (domain or "").strip().lower()
    if not domain.endswith("." + get_settings().BASE_DOMAIN.lower()):
        return False
    tenant = await resolve_tenant(db, domain)
    if tenant.kind == "admin":
        return True
    return tenant.kind == "company" and tenant.company is not None and tenant.company.is_active
