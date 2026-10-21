"""
Catálogo de referência (SUPER_ADMIN): products by sector, known by barcode (or by name without one), with their VAT
nature (never a company's rate), an optional price and their sale units; typed on the screen or imported from the
Excel sheet - importing again updates, a refused row is reported and the others go in.
"""
import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.models.reference_product import ReferenceProduct
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.reference_catalog_service import (HEADERS, ReferenceCatalogError, catalog_meta, catalog_template,
                                                    import_catalog, list_reference_products, save_reference_product)


@pytest.fixture
async def units(db, company_with_essentials):
    ctx = company_with_essentials
    found = {}
    for code, name in (("CX", "Caixa"), ("CT", "Cartão")):
        unit = (await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.code == code))).scalar_one_or_none()
        if unit is None:
            unit = UnitOfMeasureCatalog(code=code, name=name)
            db.add(unit)
            await db.flush()
        found[code] = unit.id
    await db.commit()
    return {"UN": ctx["unit_un"].id, **found, "M11": ctx["exemption_m11"].id}


async def test_a_product_with_its_sale_units(db, units):
    ovo = await save_reference_product(db, {
        "barcode": "5601", "name": "Ovos frescos", "category": "Ovos", "unit_of_measure_id": units["UN"],
        "tax_category": "ISE", "exemption_id": units["M11"], "price": None, "sectors": ["COMERCIO"],
        "units": [{"unit_of_measure_id": units["CX"], "factor": 6, "barcode": "5602"},
                  {"unit_of_measure_id": units["CT"], "factor": "30", "price": "2500"}]})
    assert ovo.price is None and [float(u.factor) for u in ovo.units] == [6, 30]
    # changed: the same unit may come back
    ovo = await save_reference_product(db, {
        "barcode": "5601", "name": "Ovos frescos", "unit_of_measure_id": units["UN"], "tax_category": "ISE",
        "exemption_id": units["M11"], "price": "100", "sectors": ["COMERCIO", "PADARIA"],
        "units": [{"unit_of_measure_id": units["CX"], "factor": 12, "barcode": "5602"}]}, ovo.id)
    assert float(ovo.price) == 100 and [(float(u.factor)) for u in ovo.units] == [12]

    for data, message in (
        ({"name": "", "sectors": ["COMERCIO"]}, "nome"),
        ({"name": "X", "barcode": "5601", "unit_of_measure_id": units["UN"], "tax_category": "NOR", "sectors": ["COMERCIO"]}, "código de barras 5601"),
        ({"name": "X", "unit_of_measure_id": units["UN"], "tax_category": "ISE", "sectors": ["COMERCIO"]}, "motivo"),
        ({"name": "X", "unit_of_measure_id": units["UN"], "tax_category": "IVA", "sectors": ["COMERCIO"]}, "natureza"),
        ({"name": "X", "unit_of_measure_id": units["UN"], "tax_category": "NOR", "sectors": ["PISCINA"]}, "Setor desconhecido"),
        ({"name": "X", "barcode": "77", "unit_of_measure_id": units["UN"], "tax_category": "NOR", "sectors": [],
          "units": [{"unit_of_measure_id": units["CX"], "factor": 6, "barcode": "77"}]}, "repetido"),
        ({"name": "X", "barcode": "77", "unit_of_measure_id": units["UN"], "tax_category": "NOR", "sectors": [],
          "units": [{"unit_of_measure_id": units["CX"], "factor": 6, "barcode": "5602"}]}, "outro produto"),
        ({"name": "X", "barcode": "5602", "unit_of_measure_id": units["UN"], "tax_category": "NOR", "sectors": []}, "unidade de venda de outro"),
        ({"name": "X", "unit_of_measure_id": units["UN"], "tax_category": "NOR", "sectors": ["COMERCIO"],
          "units": [{"unit_of_measure_id": units["UN"], "factor": 6}]}, "unidade de base"),
    ):
        with pytest.raises(ReferenceCatalogError, match=message):
            await save_reference_product(db, data)
        await db.rollback()

    found = await list_reference_products(db, "5602")  # a sale unit's barcode finds its product
    assert [p["name"] for p in found["items"]] == ["Ovos frescos"]
    assert {s["code"]: s["count"] for s in (await catalog_meta(db))["sectors"]}["PADARIA"] == 1
    # without sector: offered to every sector
    water = await save_reference_product(db, {"name": "Água 1,5L", "unit_of_measure_id": units["UN"], "tax_category": "NOR", "sectors": []})
    assert water.sectors == [] and (await catalog_meta(db))["general"] == 1
    assert [p["name"] for p in (await list_reference_products(db, sector="GERAL"))["items"]] == ["Água 1,5L"]


async def test_the_excel_sheet(db, units):
    book = load_workbook(io.BytesIO(await catalog_template(db)))
    sheet = book["Produtos"]
    assert [c.value for c in sheet[1]] == HEADERS
    sheet.delete_rows(2)
    sheet.append(["5601", "Ovos frescos", "Ovos", "UN", "ISE", "M11", "", "COMERCIO, Padaria", "CX", 6, "5602", ""])
    sheet.append([None, "Pão de forma", "Pão", "UN", "RED", "", "350", "PADARIA"])
    sheet.append(["7890", "Leite", "", "LITRO?", "NOR", "", "", "COMERCIO"])  # unknown unit
    sheet.append(["7891", "Sumo", "", "UN", "NOR", "", "", "PISCINA"])  # unknown sector
    out = io.BytesIO()
    book.save(out)
    report = await import_catalog(db, out.getvalue())
    assert (report["created"], report["updated"]) == (2, 0)
    assert [(e["row"], "Unidade" in e["message"] or "Setor" in e["message"]) for e in report["errors"]] == [(4, True), (5, True)]
    ovo = (await db.execute(select(ReferenceProduct).where(ReferenceProduct.barcode == "5601"))).scalar_one()
    assert ovo.sectors == ["COMERCIO", "PADARIA"] and float(ovo.units[0].factor) == 6

    # the same sheet again: updated, never duplicated
    report = await import_catalog(db, out.getvalue())
    assert (report["created"], report["updated"]) == (0, 2)
    with pytest.raises(ReferenceCatalogError, match="Excel"):
        await import_catalog(db, b"nada")
