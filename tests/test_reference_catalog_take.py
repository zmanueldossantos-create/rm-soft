"""
«Nova empresa» > Base > Catálogo de referência: a new company receives the catalog products of its sectors (and those
of every sector) as its own articles - stock 0, its categories, its sale units - with ITS VAT: the product's nature
gives the company's rate when its regime allows it; a regime imposing a motive (Exclusão M04) gives its exempt rate
and motive, unless the product's own motive is one the regime keeps; otherwise the article is to reclassify. Without
price: price 0, off the Caixa, never sold until priced.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models.country import Country
from app.models.fiscal_regime import FiscalRegime
from app.models.legal_vat_rate import LegalVatRate
from app.models.module import Module
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.models.product_sale_unit import ProductSaleUnit
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.vat import VAT
from app.models.vat_code import VatCode
from app.services.company_service import create_company
from app.services.reference_catalog_service import catalog_meta, catalog_offer, save_reference_product
from app.services.sector_service import seed_sector_catalog
from app.services.vat_rule_service import ArticleVatError, articles_to_reclassify, ensure_article_sellable


@pytest.fixture
async def catalog(db):
    await seed_sector_catalog(db)
    for category, name, rate in (("NOR", "Taxa normal", 14), ("RED", "Taxa reduzida", 5), ("ISE", "Isento", 0)):
        if (await db.execute(select(LegalVatRate).where(LegalVatRate.tax_category == category))).scalar_one_or_none() is None:
            db.add(LegalVatRate(tax_category=category, name=name, rate=rate))
    country = Country(code=f"X{uuid.uuid4().hex[:1]}", name="País")
    db.add(country)
    units = {}
    for code, name in (("UN", "Unidade"), ("CX", "Caixa")):
        unit = (await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.code == code))).scalar_one_or_none()
        if unit is None:
            unit = UnitOfMeasureCatalog(code=code, name=name)
            db.add(unit)
        units[code] = unit
    await db.flush()
    motives = {}
    for code in ("M10", "M04"):
        motive = (await db.execute(select(VatCode).where(VatCode.code == code))).scalar_one_or_none()
        if motive is None:
            motive = VatCode(code=code, name="Isento - motivo de teste " + code, rate=0, country_id=country.id, valid_from=date(2020, 1, 1))
            db.add(motive)
        motives[code] = motive
    await db.flush()
    regimes = {
        "geral": FiscalRegime(name=f"Geral {uuid.uuid4().hex[:5]}"),
        "exclusao": FiscalRegime(name=f"Exclusão {uuid.uuid4().hex[:5]}", allows_nor=False, allows_red=False,
                                 required_exemption_id=motives["M04"].id, kept_exemption_ids=[motives["M10"].id]),
        "so_normal": FiscalRegime(name=f"Só normal {uuid.uuid4().hex[:5]}", allows_red=False, allows_ise=False),
    }
    db.add_all(regimes.values())
    await db.commit()
    un, cx = units["UN"].id, units["CX"].id
    await save_reference_product(db, {"barcode": "5601", "name": "Ovos frescos", "category": "Ovos", "unit_of_measure_id": un,
                                      "tax_category": "ISE", "exemption_id": motives["M10"].id, "sectors": ["COMERCIO"],
                                      "units": [{"unit_of_measure_id": cx, "factor": 6, "barcode": "5602"}]})
    await save_reference_product(db, {"name": "Pão de forma", "category": "Pão", "unit_of_measure_id": un,
                                      "tax_category": "RED", "price": 350, "sectors": ["PADARIA"]})
    await save_reference_product(db, {"barcode": "7001", "name": "Água 1,5L", "category": "Bebidas", "unit_of_measure_id": un,
                                      "tax_category": "NOR", "price": 100, "sectors": [],
                                      "units": [{"unit_of_measure_id": cx, "factor": 6}]})
    await save_reference_product(db, {"barcode": "7002", "name": "Cimento", "unit_of_measure_id": un,
                                      "tax_category": "NOR", "price": 5000, "sectors": ["BAR"]})
    modules = {m.code: m.id for m in (await db.execute(select(Module))).scalars().all()}
    return {"regimes": {k: r.id for k, r in regimes.items()}, "modules": modules, "motives": motives}


async def _new(db, regime_id, module_codes, modules, reference_catalog=True):
    n = uuid.uuid4().int % 10**9
    return await create_company(
        db, name=f"Loja {n}", nif=f"5{n:09d}", email=f"l{n}@t.ao", phone_number=f"+2449{n % 10**8:08d}",
        gestor_full_name="Gestor", gestor_phone_number=f"+2449{(n + 3) % 10**8:08d}", gestor_password="Teste@2026",
        fiscal_regime_id=regime_id, module_ids=[modules[c] for c in module_codes], reference_catalog=reference_catalog)


async def test_a_shop_receives_its_sectors_products_with_its_vat(db, catalog):
    offer = await catalog_offer(db, [catalog["modules"]["COMERCIO"]])
    assert (offer["products"], offer["without_price"]) == (2, 1)  # eggs (its sector) and water (every sector)
    shop = await _new(db, catalog["regimes"]["geral"], ["COMERCIO"], catalog["modules"])
    assert shop.catalog_counts == {"artigos": 2, "sem_preco": 1, "a_rever": 0, "unidades_de_venda": 2, "categorias": 2}
    products = {p.name: p for p in (await db.execute(select(Product).where(Product.company_id == shop.id))).scalars()}
    assert set(products) == {"Ovos frescos", "Água 1,5L"}  # never the bar's cement, nor the bakery's bread
    vats = {v.id: v for v in (await db.execute(select(VAT).where(VAT.company_id == shop.id))).scalars()}
    eggs, water = products["Ovos frescos"], products["Água 1,5L"]
    assert (vats[eggs.vat_id].tax_category, eggs.exemption_reason_id) == ("ISE", catalog["motives"]["M10"].id)
    assert (vats[water.vat_id].tax_category, float(water.price), water.code) == ("NOR", 100, "7001")
    assert (await db.get(ProductCategory, eggs.category_id)).name == "Ovos"
    # without price: off the Caixa, never sold until priced
    assert (float(eggs.price), eggs.awaiting_price, eggs.not_available_pos) == (0, True, True)
    with pytest.raises(ArticleVatError, match="ainda não tem preço"):
        await ensure_article_sellable(db, eggs)
    units = {(await db.get(Product, u.product_id)).name: u for u in (await db.execute(
        select(ProductSaleUnit).where(ProductSaleUnit.company_id == shop.id))).scalars()}
    assert (units["Ovos frescos"].barcode, float(units["Água 1,5L"].price)) == ("5602", 600)  # 6 × 100


async def test_the_regime_decides_the_vat(db, catalog):
    # Exclusão: every product exempt with the regime's motive - but eggs keep their own (M10 kept by the regime)
    shop = await _new(db, catalog["regimes"]["exclusao"], ["COMERCIO"], catalog["modules"])
    products = {p.name: p for p in (await db.execute(select(Product).where(Product.company_id == shop.id))).scalars()}
    assert products["Água 1,5L"].exemption_reason_id == catalog["motives"]["M04"].id
    assert products["Ovos frescos"].exemption_reason_id == catalog["motives"]["M10"].id
    assert shop.catalog_counts["a_rever"] == 0

    # a regime allowing neither the reduced rate nor exemption: the bread comes, to reclassify, never sold before
    bakery = await _new(db, catalog["regimes"]["so_normal"], ["PADARIA"], catalog["modules"])
    assert bakery.catalog_counts["a_rever"] == 1
    assert [p["name"] for p in (await articles_to_reclassify(db, bakery.id))["products"]] == ["Pão de forma"]


async def test_the_catalogs_motives_are_a_products_own(db, catalog):
    codes = {m["code"] for m in (await catalog_meta(db))["exemptions"]}
    assert catalog["motives"]["M10"].code in codes and catalog["motives"]["M04"].code not in codes  # M04: a regime's


async def test_priced_at_last_it_is_on_sale_with_its_packs(db, catalog):
    from app.services.product_service import update_product
    shop = await _new(db, catalog["regimes"]["geral"], ["COMERCIO"], catalog["modules"])
    eggs = (await db.execute(select(Product).where(Product.company_id == shop.id, Product.name == "Ovos frescos"))).scalar_one()
    await update_product(db, shop.id, eggs.id, code=eggs.code, name=eggs.name, barcode=eggs.barcode, vat_id=eggs.vat_id,
                         price=150, min_stock_threshold=0, unit_of_measure_id=eggs.unit_of_measure_id,
                         category_id=eggs.category_id, not_available_pos=True, exemption_reason_id=eggs.exemption_reason_id)
    await db.refresh(eggs)
    assert (eggs.awaiting_price, eggs.not_available_pos) == (False, False)
    await ensure_article_sellable(db, eggs)  # on sale now
    [box] = (await db.execute(select(ProductSaleUnit).where(ProductSaleUnit.product_id == eggs.id))).scalars().all()
    assert float(box.price) == 900  # 6 × 150


async def test_the_packs_follow_the_unit_price_unless_priced_on_their_own(db, catalog):
    from app.services.product_service import update_product
    shop = await _new(db, catalog["regimes"]["geral"], ["COMERCIO"], catalog["modules"])
    water = (await db.execute(select(Product).where(Product.company_id == shop.id, Product.name == "Água 1,5L"))).scalar_one()
    [pack] = (await db.execute(select(ProductSaleUnit).where(ProductSaleUnit.product_id == water.id))).scalars().all()

    async def price(value):
        await update_product(db, shop.id, water.id, code=water.code, name=water.name, barcode=water.barcode, vat_id=water.vat_id,
                             price=value, min_stock_threshold=0, unit_of_measure_id=water.unit_of_measure_id,
                             category_id=water.category_id)
        await db.refresh(pack)
    await price(120)
    assert float(pack.price) == 720  # 6 × 100 followed: 6 × 120
    pack.price = 650  # a box price of its own
    await db.commit()
    await price(130)
    assert float(pack.price) == 650  # kept


async def test_an_existing_shop_picks_from_the_catalog(db, catalog):
    from app.services.reference_catalog_service import company_catalog, lookup_barcode, take_for_company
    shop = await _new(db, catalog["regimes"]["geral"], ["COMERCIO"], catalog["modules"], reference_catalog=False)
    offer = await company_catalog(db, shop.id)  # its sectors and every sector: eggs, water - not the bar's cement
    assert {i["name"] for i in offer["items"]} == {"Água 1,5L", "Ovos frescos"} and not any(i["owned"] for i in offer["items"])
    assert {i["name"] for i in (await company_catalog(db, shop.id, mine=False))["items"]} >= {"Cimento", "Pão de forma"}

    found = await lookup_barcode(db, shop.id, "5602")  # a pack's barcode finds its product
    assert (found["name"], found["owned"]) == ("Ovos frescos", False)
    assert await lookup_barcode(db, shop.id, "999") is None

    taken = await take_for_company(db, shop.id, [found["id"]])
    assert (taken["artigos"], taken["sem_preco"], taken["ignorados"], len(taken["product_ids"])) == (1, 1, 0, 1)
    assert (await lookup_barcode(db, shop.id, "5601"))["owned"] is True
    again = await take_for_company(db, shop.id, [found["id"]])
    assert (again["artigos"], again["ignorados"]) == (0, 1)  # never twice
