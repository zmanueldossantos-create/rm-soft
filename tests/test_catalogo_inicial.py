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
    assert await _count(db, Resource, company.id) == 7  # Executivo 101-104 + Clássico 201-203
    from app.models.service import Service
    rates = {s.code: s for s in (await db.execute(select(Service).where(Service.company_id == company.id))).scalars().all()}
    assert rates["EXE-DIA"].duration_minutes is None and float(rates["EXE-DIA"].price) == 35000  # the night: per night
    assert rates["CLA-2H"].duration_minutes == 120 and float(rates["CLA-2H"].price) == 5000  # timed: per started slice
    assert rates["EXE-1H"].resource_type_id == rates["EXE-DIA"].resource_type_id != rates["CLA-1H"].resource_type_id
    assert any("Day use Clássico" in line and "480 min" in line for line in hotel["criados"])
    hotel_activity = (await db.execute(select(Activity).where(Activity.company_id == company.id, Activity.name == "Hotel"))).scalars().one()
    assert rates["HOT-PEQ"].activity_ids == [hotel_activity.id]  # a hotel service: at the hotel's tills only


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
