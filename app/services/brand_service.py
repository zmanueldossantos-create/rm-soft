"""
Marca do software: the name and logo the users of an installation see - the menu, the login screen, the browser's tab,
the footer, the help. A client with a local installation may have the software under its own name (contract decided by
RM SOFT): only the SUPER_ADMIN sets it. Without a brand, RM SOFT. The documents already carry the company's own
identity; the producer's identity for the AGT and the SAF-T is separate (platform_settings.vendor_tax_id, product_id...).
"""
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_settings_service import get_or_create_platform_settings

DEFAULT_NAME = "RM SOFT"
VENDOR = "RM SOFT"
HEADERS = ("NOME", "LOGO")
LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")  # no SVG: it may carry code, served from our own address
MAX_LOGO_BYTES = 1024 * 1024  # 1 MB
LOGO_DIR = os.path.join("uploads", "brand")


class BrandError(Exception):
    """A brand setting refused (PT-PT message for the toast)."""


def view(settings) -> dict:
    """What every screen needs (public: the login screen shows it before any session)."""
    name = (settings.brand_name or "").strip() or DEFAULT_NAME
    logo = settings.brand_logo_path
    return {
        "name": name,
        "logo_path": logo,
        # the logo in the menu only when there is one
        "header": "LOGO" if settings.brand_header == "LOGO" and logo else "NOME",
        "header_choice": settings.brand_header,
        # «Desenvolvido por RM SOFT»: only meaningful under another name
        "vendor": VENDOR if settings.brand_show_vendor and name != DEFAULT_NAME else None,
        "show_vendor": settings.brand_show_vendor,
        "custom": name != DEFAULT_NAME,
    }


async def brand_name(db: AsyncSession) -> str:
    return view(await get_or_create_platform_settings(db))["name"]


async def get_brand(db: AsyncSession) -> dict:
    return view(await get_or_create_platform_settings(db))


async def update_brand(db: AsyncSession, name: str | None, header: str, show_vendor: bool) -> dict:
    if header not in HEADERS:
        raise BrandError("Escolha o que o menu mostra: o nome ou o logótipo")
    name = (name or "").strip()
    if len(name) > 60:
        raise BrandError("O nome do software tem no máximo 60 caracteres")
    settings = await get_or_create_platform_settings(db)
    if header == "LOGO" and not settings.brand_logo_path:
        raise BrandError("Carregue primeiro o logótipo para o mostrar no menu")
    settings.brand_name = name or None
    settings.brand_header = header
    settings.brand_show_vendor = show_vendor
    await db.commit()
    return view(settings)


def _remove_logo_files() -> None:
    for ext in LOGO_EXTENSIONS:
        path = os.path.join(LOGO_DIR, "logo" + ext)
        if os.path.exists(path):
            os.remove(path)


async def set_logo(db: AsyncSession, filename: str | None, content: bytes) -> dict:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in LOGO_EXTENSIONS:
        raise BrandError("Formato de imagem inválido - use PNG, JPG ou WEBP")
    if len(content) > MAX_LOGO_BYTES:
        raise BrandError("Imagem demasiado grande - máximo 1 MB")
    os.makedirs(LOGO_DIR, exist_ok=True)
    _remove_logo_files()  # a new logo with another extension leaves no orphan
    with open(os.path.join(LOGO_DIR, "logo" + ext), "wb") as f:
        f.write(content)
    settings = await get_or_create_platform_settings(db)
    # the version in the address: the browsers do not keep showing the old picture
    settings.brand_logo_path = f"/uploads/brand/logo{ext}?v={os.urandom(3).hex()}"
    await db.commit()
    return view(settings)


async def remove_logo(db: AsyncSession) -> dict:
    _remove_logo_files()
    settings = await get_or_create_platform_settings(db)
    settings.brand_logo_path = None
    settings.brand_header = "NOME"
    await db.commit()
    return view(settings)
