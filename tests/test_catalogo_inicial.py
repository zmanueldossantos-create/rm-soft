"""Catálogo inicial: the base of a new client loaded from a JSON file (app/tools/catalogo_inicial.py) - categories,
suppliers, raw materials, articles, services, recipes, customers, purchases with their stock entry, and the hotel."""
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models.activity import Activity
from app.models.company_module import CompanyModule
from app.models.module import Module
from app.models.movement_type import MovementDirection, MovementType
from app.models.product import Product
from app.models.purchase_invoice import PurchaseInvoice
from app.models.recipe_ingredient import RecipeIngredient
from app.models.resource import Resource
from app.models.stock import Stock
from app.models.supplier import Supplier
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.activity_service import create_activity
from app.tools.catalogo_inicial import CatalogError, load

FILES = Path(__file__).parent.parent / "instalador" / "catalogos"
FILE = FILES / "meldarocha_padaria.json"
HOTEL = FILES / "meldarocha_hotel.json"


async def _prepare(db, company_id, *modules):
    if (await db.execute(select(MovementType).where(MovementType.is_auto.is_(True)))).first() is None:
        db.add_all([MovementType(code="EAL", name="Entrada automática", direction=MovementDirection.ENTRADA, is_auto=True),
                    MovementType(code="SAL", name="Saída automática", direction=MovementDirection.SAIDA, is_auto=True)])
    for code, name in (("KG", "Quilograma"), ("L", "Litro")):  # fractional, as the platform's catalog has them
        if (await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.code == code))).scalar_one_or_none() is None:
            db.add(UnitOfMeasureCatalog(code=code, name=name, is_fractional=True))
    for name in modules:
        module = Module(name=name)
        db.add(module)
        await db.flush()
        db.add(CompanyModule(company_id=company_id, module_id=module.id, is_enabled=True))
    await db.commit()


async def _count(db, model, company_id):
    return (await db.execute(select(func.count()).select_from(model).where(model.company_id == company_id))).scalar_one()


@pytest.mark.asyncio
async def test_the_mel_da_rocha_base(db, company_with_essentials, legal_vat_rates):
    company = company_with_essentials["company"]
    await _prepare(db, company.id, "Padaria")
    data = json.loads(FILE.read_text(encoding="utf-8"))

    check = await load(db, company.nif, data, dry_run=True)  # a check changes nothing
    assert any("Receita de PAO01" in line for line in check["criados"]) and await _count(db, Supplier, company.id) == 0

    await load(db, company.nif, data)
    assert await _count(db, Supplier, company.id) == len(data["fornecedores"])
    assert await _count(db, Product, company.id) == len(data["materias_primas"]) + len(data["produtos"])
    assert (await db.execute(select(func.count(func.distinct(RecipeIngredient.finished_product_id)))
                             .where(RecipeIngredient.company_id == company.id))).scalar_one() == len(data["receitas"])
    assert await _count(db, PurchaseInvoice, company.id) == 0  # a catalog only: the movements are made in the training
    flour = (await db.execute(select(Product).where(Product.company_id == company.id, Product.code == "MP01"))).scalar_one()
    assert flour.is_raw_material and flour.not_available_pos

    again = await load(db, company.nif, data)  # run again: nothing duplicated
    assert not again["criados"] and await _count(db, Supplier, company.id) == len(data["fornecedores"])


@pytest.mark.asyncio
async def test_purchases_go_to_the_activity_the_gestor_made(db, company_with_essentials, legal_vat_rates):
    company = company_with_essentials["company"]
    await _prepare(db, company.id, "Padaria")
    padaria = (await db.execute(select(Module).where(Module.name == "Padaria"))).scalar_one()
    own = await create_activity(db, company.id, padaria.id, "Padaria Mel")  # named by the gestor: reused, never doubled
    data = {"fornecedores": [{"nome": "Moagem", "nif": "5000999291"}],
            "materias_primas": [{"codigo": "MP01", "nome": "Farinha", "unidade": "KG"}],
            "compras": [{"fornecedor": "Moagem", "documento": "FT 1", "linhas": [{"codigo": "MP01", "quantidade": 100, "preco": 900}]}]}
    report = await load(db, company.nif, data)
    assert "Atividade Padaria Mel (módulo Padaria)" in report["existentes"]
    assert (await db.execute(select(func.count()).select_from(Activity).where(
        Activity.company_id == company.id, Activity.module_id == padaria.id))).scalar_one() == 1
    flour = (await db.execute(select(Product).where(Product.company_id == company.id, Product.code == "MP01"))).scalar_one()
    stock = (await db.execute(select(Stock.quantity).where(Stock.product_id == flour.id,
                                                           Stock.warehouse_id == own.warehouse_id))).scalar_one()
    assert float(stock) == 100 and await _count(db, PurchaseInvoice, company.id) == 1


@pytest.mark.asyncio
async def test_the_hotel_comes_with_its_module(db, company_with_essentials, legal_vat_rates):
    company = company_with_essentials["company"]
    await _prepare(db, company.id)
    hotel_data = json.loads(HOTEL.read_text(encoding="utf-8"))
    early = await load(db, company.nif, hotel_data)  # the Hotel module not granted yet: nothing of it
    assert any("módulo Hotel ainda não está ativo" in line for line in early["ignorados"])
    await _prepare(db, company.id, "Hotel")
    hotel = await load(db, company.nif, hotel_data)
    assert await _count(db, Resource, company.id) == 7  # Complexo VIP: Luanda... Huambo; Standard: Massabi, Soyo, Uíge
    from app.models.resource import ResourceRatePrice
    from app.models.service import Service
    rates = {s.code: s for s in (await db.execute(select(Service).where(Service.company_id == company.id))).scalars().all()}
    assert rates["VIP-DIA"].duration_minutes is None and float(rates["VIP-DIA"].price) == 30000  # at the type's hours
    assert rates["STD-2H"].duration_minutes == 120 and float(rates["STD-2H"].price) == 6000  # timed: per started slice
    assert (rates["VIP-PER"].stay_start_time.strftime("%H:%M"), rates["VIP-PER"].stay_end_time.strftime("%H:%M")) == ("22:00", "07:30")
    assert rates["VIP-1H"].resource_type_id == rates["VIP-DIA"].resource_type_id != rates["STD-1H"].resource_type_id
    # the rooms with their own prices: Benguela and Huambo (4 each), Soyo (2), Uíge (4)
    assert await _count(db, ResourceRatePrice, company.id) == 14
    assert any("Uíge" in line and "4 preço(s) próprio(s)" in line for line in hotel["criados"])
    hotel_activity = (await db.execute(select(Activity).where(Activity.company_id == company.id, Activity.name == "Hotel"))).scalars().one()
    assert rates["HOT-REF"].activity_ids == [hotel_activity.id]  # a hotel service: at the hotel's tills only


@pytest.mark.asyncio
async def test_what_is_refused(db, company_with_essentials, legal_vat_rates):
    company = company_with_essentials["company"]
    with pytest.raises(CatalogError, match="Nenhuma empresa"):
        await load(db, "999", {})
    with pytest.raises(CatalogError, match="Faltam unidades"):
        await load(db, company.nif, {"materias_primas": [{"codigo": "X", "nome": "X", "unidade": "TON"}]})
    await _prepare(db, company.id)
    with pytest.raises(CatalogError, match="tem de ser maior que zero"):
        await load(db, company.nif, {"produtos": [{"codigo": "X", "nome": "X", "preco": 0}]})
    with pytest.raises(CatalogError, match="categoria «Nada» desconhecida"):
        await load(db, company.nif, {"produtos": [{"codigo": "X", "nome": "X", "preco": 10, "categoria": "Nada"}]})


def test_the_file_is_a_small_catalog_that_leaves_the_rest_to_the_training():
    data = json.loads(FILE.read_text(encoding="utf-8"))
    codes = {p["codigo"] for p in data["materias_primas"] + data["produtos"]}
    assert len(codes) == len(data["materias_primas"]) + len(data["produtos"])
    for recipe in data["receitas"]:
        assert recipe["produto"] in codes and all(i["codigo"] in codes for i in recipe["ingredientes"])
    assert len(data["categorias"]) == 5 and len(data["receitas"]) == 5
    assert {p["categoria"] for p in data["produtos"]} == set(data["categorias"])  # every category has its articles
    assert not data.get("compras") and "hotel" not in data  # no movement, the Padaria only
    assert {p["codigo"] for p in data["produtos"] if "custo" in p} == {"BEB02"}  # only what is bought ready


@pytest.mark.asyncio
async def test_a_company_already_selling_takes_a_catalog_but_never_purchases(db, company_with_essentials, legal_vat_rates):
    """The Hotel granted after the Padaria has sold: its catalog loads (nothing existing touched); a file with
    «compras» (documents and stock) stays for a company that is starting."""
    from app.services.invoice_service import create_invoice
    ctx = company_with_essentials
    company = ctx["company"]
    await _prepare(db, company.id)
    await load(db, company.nif, {"servicos": [{"codigo": "ENT-T", "nome": "Entrega", "preco": 1000}]})
    from app.models.service import Service
    entrega = (await db.execute(select(Service).where(Service.company_id == company.id, Service.code == "ENT-T"))).scalar_one()
    await create_invoice(db, company.id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA_RECIBO",
                         lines_input=[{"service_id": entrega.id, "quantity": 1}])  # a real sale (not training)
    await load(db, company.nif, {"servicos": [{"codigo": "ENT-T2", "nome": "Entrega 2", "preco": 2000}]})
    assert (await db.execute(select(Service).where(Service.company_id == company.id, Service.code == "ENT-T2"))).first()
    with pytest.raises(CatalogError, match="compras"):
        await load(db, company.nif, {"compras": [{"fornecedor": "X"}]})
