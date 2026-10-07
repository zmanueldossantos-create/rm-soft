"""Point 43 - products and services share one list of codes in the SAF-T: a code is unique across both."""
import pytest

from app.models.product import Product, ProductType
from app.models.service import Service
from app.services import product_service, service_service


@pytest.mark.asyncio
async def test_a_service_cannot_take_a_products_code(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    db.add(Product(company_id=cid, code="DUP-1", name="Muamba", vat_id=ctx["vat_ise"].id, price=4500,
                   min_stock_threshold=0, product_type=ProductType.BEM))
    await db.commit()
    with pytest.raises(service_service.ServiceAlreadyExistsError, match="produto registado"):
        await service_service._check_fields_available(db, cid, "dup-1", "Outro nome")   # any case


@pytest.mark.asyncio
async def test_a_product_cannot_take_a_services_code(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    db.add(Service(company_id=cid, code="DUP-2", name="Consulta", vat_id=ctx["vat_ise"].id, price=1000))
    await db.commit()
    with pytest.raises(product_service.ProductAlreadyExistsError, match="servico registado"):
        await product_service._check_all_fields_available(db, cid, "DUP-2", "Outro nome", None)
