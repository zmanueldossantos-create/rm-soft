"""
«Nova empresa» > Base: a new company made with the catalog of another company's backup file (a «Comércio geral»
prepared once). Copied: categories, articles (price, units, recipes - never stock or cost), services, suppliers - with
new ids, linked to the new company's own rows. Never: customers, documents, stock. The new company must take the
file's fiscal regime; nothing chosen or another regime: refused, nothing created.
"""
import uuid

import pytest
from sqlalchemy import func, select

from app.models.company import Company
from app.models.customer import Customer
from app.models.fiscal_regime import FiscalRegime
from app.models.legal_vat_rate import LegalVatRate
from app.models.product import Product, ProductType
from app.models.product_category import ProductCategory
from app.models.product_sale_unit import ProductSaleUnit
from app.models.recipe_ingredient import RecipeIngredient
from app.models.service import Service
from app.models.service_type import ServiceType
from app.models.stock import Stock
from app.models.supplier import Supplier
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.vat import VAT
from app.services.company_backup_service import BackupError, export_company
from app.services.company_base_service import inspect_base
from app.services.company_service import create_company


async def _new_company(db, regime_id, **base):
    n = uuid.uuid4().int % 10**9
    return await create_company(
        db, name=f"Loja Nova {n}", nif=f"5{n:09d}", email=f"loja{n}@teste.ao", phone_number=f"+2449{n % 10**8:08d}",
        gestor_full_name="Gestor Loja", gestor_phone_number=f"+2449{(n + 7) % 10**8:08d}", gestor_password="Teste@2026",
        fiscal_regime_id=regime_id, **base)


@pytest.fixture
async def base_file(db, company_with_essentials):
    """A «Comércio geral» with its catalog, a customer and some stock - exported to a file."""
    ctx = company_with_essentials
    company = ctx["company"]
    regime = FiscalRegime(name=f"Regime Geral {uuid.uuid4().hex[:6]}")
    db.add(regime)
    for category, name, rate in (("NOR", "Taxa normal", 14), ("RED", "Taxa reduzida", 5), ("ISE", "Isento", 0)):
        if (await db.execute(select(LegalVatRate).where(LegalVatRate.tax_category == category))).scalar_one_or_none() is None:
            db.add(LegalVatRate(tax_category=category, name=name, rate=rate))
    await db.flush()
    company.fiscal_regime_id = regime.id
    box = (await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.code == "CX"))).scalar_one_or_none()
    if box is None:
        box = UnitOfMeasureCatalog(code="CX", name="Caixa")
        db.add(box)
    category = ProductCategory(company_id=company.id, name="Bebidas")
    db.add(category)
    await db.flush()
    sumo = Product(company_id=company.id, code="SUMO", name="Sumo", vat_id=ctx["vat_red"].id, price=500, average_cost=320,
                   category_id=category.id, min_stock_threshold=0, product_type=ProductType.BEM,
                   unit_of_measure_id=ctx["unit_un"].id, barcode="5601234")
    acucar = Product(company_id=company.id, code="ACUCAR", name="Açúcar", vat_id=ctx["vat_nor"].id, price=900,
                     min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                     is_raw_material=True)
    db.add_all([sumo, acucar])
    await db.flush()
    db.add(ProductSaleUnit(company_id=company.id, product_id=sumo.id, unit_of_measure_id=box.id, factor=12, price=5500))
    db.add(RecipeIngredient(company_id=company.id, finished_product_id=sumo.id, ingredient_product_id=acucar.id,
                            quantity_per_batch=2))
    db.add(Stock(company_id=company.id, product_id=sumo.id, warehouse_id=ctx["central_warehouse"].id, quantity=40))
    service_type = ServiceType(company_id=company.id, name="Entregas")
    db.add(service_type)
    await db.flush()
    db.add(Service(company_id=company.id, code="ENTREGA", name="Entrega ao domicílio", service_type_id=service_type.id,
                   vat_id=ctx["vat_nor"].id, price=1000))
    db.add(Supplier(company_id=company.id, name="Distribuidora Kwanza"))
    db.add(Customer(company_id=company.id, name="Cliente do Modelo", nif="5000000001"))
    await db.commit()
    content, _ = await export_company(db, company.id)
    return content, regime.id, company.id


async def test_a_company_made_from_a_base_file(db, base_file):
    content, regime_id, source_id = base_file
    seen = await inspect_base(db, content)
    assert (seen["counts"], seen["fiscal_regime_id"], seen["problems"]) == (
        {"artigos": 2, "servicos": 1, "fornecedores": 1}, regime_id, [])

    new = await _new_company(db, regime_id, base_token=seen["token"], base_parts=["artigos", "servicos", "fornecedores"])
    assert new.base_counts == {"categorias": 1, "artigos": 2, "unidades_de_venda": 1, "receitas": 1,
                               "tipos_de_servico": 1, "servicos": 1, "fornecedores": 1}
    products = {p.code: p for p in (await db.execute(select(Product).where(Product.company_id == new.id))).scalars()}
    sumo = products["SUMO"]
    assert (float(sumo.price), sumo.barcode, sumo.average_cost) == (500, "5601234", None)  # price yes, cost never
    own_vats = {v.id: v for v in (await db.execute(select(VAT).where(VAT.company_id == new.id))).scalars()}
    assert own_vats[sumo.vat_id].tax_category == "RED" and own_vats[products["ACUCAR"].vat_id].tax_category == "NOR"
    category = await db.get(ProductCategory, sumo.category_id)
    assert (category.company_id, category.name) == (new.id, "Bebidas")
    [unit] = (await db.execute(select(ProductSaleUnit).where(ProductSaleUnit.company_id == new.id))).scalars().all()
    assert (unit.product_id, float(unit.price)) == (sumo.id, 5500)
    [recipe] = (await db.execute(select(RecipeIngredient).where(RecipeIngredient.company_id == new.id))).scalars().all()
    assert (recipe.finished_product_id, recipe.ingredient_product_id) == (sumo.id, products["ACUCAR"].id)
    [service] = (await db.execute(select(Service).where(Service.company_id == new.id))).scalars().all()
    assert own_vats[service.vat_id].tax_category == "NOR"
    assert (await db.get(ServiceType, service.service_type_id)).company_id == new.id

    async def count(model, company_id):
        return (await db.execute(select(func.count()).select_from(model).where(model.company_id == company_id))).scalar_one()
    assert await count(Supplier, new.id) == 1
    assert await count(Customer, new.id) == 0 and await count(Stock, new.id) == 0  # never clients, never stock
    assert await count(Product, source_id) == 2  # the file's company is untouched


async def test_only_the_parts_chosen_and_only_the_files_regime(db, base_file):
    content, regime_id, _ = base_file
    seen = await inspect_base(db, content)
    new = await _new_company(db, regime_id, base_token=seen["token"], base_parts=["fornecedores"])
    assert new.base_counts == {"fornecedores": 1}
    assert (await db.execute(select(func.count()).select_from(Product).where(Product.company_id == new.id))).scalar_one() == 0
    with pytest.raises(BackupError, match="expirado"):  # a file is used once
        await _new_company(db, regime_id, base_token=seen["token"], base_parts=["artigos"])

    other = FiscalRegime(name=f"Regime Simplificado {uuid.uuid4().hex[:6]}", allows_nor=False, allows_red=False)
    db.add(other)
    await db.commit()
    other_id = other.id
    companies_before = (await db.execute(select(func.count()).select_from(Company))).scalar_one()
    token = (await inspect_base(db, content))["token"]
    with pytest.raises(BackupError, match="regime fiscal"):
        await _new_company(db, other_id, base_token=token, base_parts=["artigos"])
    with pytest.raises(BackupError, match="Escolha"):
        await _new_company(db, regime_id, base_token=token, base_parts=[])
    assert (await db.execute(select(func.count()).select_from(Company))).scalar_one() == companies_before  # nothing created
