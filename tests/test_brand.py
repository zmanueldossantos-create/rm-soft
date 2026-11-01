"""Marca do software: the name and logo the users of an installation see (SUPER_ADMIN, Configurações → Sistema)."""
import os

import pytest

from app.services import brand_service
from app.services.brand_service import BrandError

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.mark.asyncio
async def test_without_a_brand_rm_soft(db):
    brand = await brand_service.get_brand(db)
    assert brand["name"] == "RM SOFT" and brand["header"] == "NOME" and brand["vendor"] is None and not brand["custom"]


@pytest.mark.asyncio
async def test_a_clients_name_and_the_vendor_line(db):
    brand = await brand_service.update_brand(db, "  MDR Gestão ", "NOME", True)
    assert brand["name"] == "MDR Gestão" and brand["custom"] and brand["vendor"] == "RM SOFT"
    brand = await brand_service.update_brand(db, "MDR Gestão", "NOME", False)
    assert brand["vendor"] is None
    brand = await brand_service.update_brand(db, "", "NOME", True)  # empty: back to RM SOFT
    assert brand["name"] == "RM SOFT" and brand["vendor"] is None


@pytest.mark.asyncio
async def test_the_logo_in_the_menu(db):
    with pytest.raises(BrandError, match="Carregue primeiro o logótipo"):
        await brand_service.update_brand(db, "MDR", "LOGO", True)
    with pytest.raises(BrandError, match="Formato de imagem inválido"):
        await brand_service.set_logo(db, "logo.svg", b"<svg/>")
    try:
        brand = await brand_service.set_logo(db, "MDR logo.PNG", PNG)
        assert brand["logo_path"].startswith("/uploads/brand/logo.png?v=")
        assert os.path.exists(os.path.join("uploads", "brand", "logo.png"))
        brand = await brand_service.update_brand(db, "MDR", "LOGO", True)
        assert brand["header"] == "LOGO"
        brand = await brand_service.remove_logo(db)  # without a logo the menu shows the name again
        assert brand["logo_path"] is None and brand["header"] == "NOME"
        assert not os.path.exists(os.path.join("uploads", "brand", "logo.png"))
    finally:
        brand_service._remove_logo_files()
