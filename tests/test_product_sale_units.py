"""Sale units of a product: rules checked by the service (base unit, duplicate, barcode, factor), deactivation."""
import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.product_sale_unit_service import (
    SaleUnitInvalidError, create_sale_unit, list_sale_units, toggle_sale_unit, update_sale_unit,
)


async def _setup(db, ctx):
    company_id = ctx["company"].id
    egg = UnitOfMeasureCatalog(code="UN", name="Unidade")
    pallet = UnitOfMeasureCatalog(code="PAL", name="Palete")
    box = UnitOfMeasureCatalog(code="CX", name="Caixa")
    db.add_all([egg, pallet, box])
    await db.commit()
    for u in (egg, pallet, box):
        await db.refresh(u)
    product = Product(company_id=company_id, code="OVO", name="Ovo", vat_id=ctx["vat_nor"].id, price=125.0,
                      min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=egg.id, barcode="5600000000001")
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return company_id, product.id, egg.id, pallet.id, box.id


@pytest.mark.asyncio
async def test_a_pallet_of_30_eggs_is_created_and_listed(db, company_with_essentials):
    company_id, product_id, egg_id, pallet_id, box_id = await _setup(db, company_with_essentials)
    unit = await create_sale_unit(db, company_id, product_id, pallet_id, 30, 3000, "5600000000030")
    assert (unit.unit_of_measure_code, float(unit.factor), float(unit.price), unit.is_active) == ("PAL", 30.0, 3000.0, True)
    listed = await list_sale_units(db, company_id, product_id)
    assert [u.unit_of_measure_code for u in listed] == ["PAL"]


@pytest.mark.asyncio
async def test_the_base_unit_or_a_duplicate_unit_is_refused(db, company_with_essentials):
    company_id, product_id, egg_id, pallet_id, box_id = await _setup(db, company_with_essentials)
    with pytest.raises(SaleUnitInvalidError, match="unidade base"):
        await create_sale_unit(db, company_id, product_id, egg_id, 1, 125)
    await create_sale_unit(db, company_id, product_id, pallet_id, 30, 3000)
    with pytest.raises(SaleUnitInvalidError, match="ja tem esta unidade"):
        await create_sale_unit(db, company_id, product_id, pallet_id, 24, 2800)


@pytest.mark.asyncio
async def test_a_barcode_is_unique_across_products_and_sale_units(db, company_with_essentials):
    company_id, product_id, egg_id, pallet_id, box_id = await _setup(db, company_with_essentials)
    with pytest.raises(SaleUnitInvalidError, match="codigo de barras"):
        await create_sale_unit(db, company_id, product_id, pallet_id, 30, 3000, "5600000000001")  # the egg's own barcode
    await create_sale_unit(db, company_id, product_id, pallet_id, 30, 3000, "5600000000030")
    with pytest.raises(SaleUnitInvalidError, match="codigo de barras"):
        await create_sale_unit(db, company_id, product_id, box_id, 12, 1400, "5600000000030")


@pytest.mark.asyncio
async def test_a_sale_unit_is_updated_and_deactivated_never_deleted(db, company_with_essentials):
    company_id, product_id, egg_id, pallet_id, box_id = await _setup(db, company_with_essentials)
    unit = await create_sale_unit(db, company_id, product_id, pallet_id, 30, 3000, "5600000000030")
    updated = await update_sale_unit(db, company_id, product_id, unit.id, pallet_id, 30, 2900, "5600000000030")
    assert float(updated.price) == 2900.0
    toggled = await toggle_sale_unit(db, company_id, product_id, unit.id)
    assert toggled.is_active is False
    assert len(await list_sale_units(db, company_id, product_id)) == 1


from app.models.company import Company  # noqa: E402
from app.services.product_sale_unit_service import SaleUnitNeedsConfirmationError  # noqa: E402


async def _set_check(db, company_id, column, mode):
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one()
    setattr(company, column, mode)
    await db.commit()


@pytest.mark.asyncio
async def test_a_factor_of_one_or_a_wrong_fixed_factor_is_always_refused(db, company_with_essentials):
    company_id, product_id, egg_id, pallet_id, box_id = await _setup(db, company_with_essentials)
    dozen = UnitOfMeasureCatalog(code="DZ", name="Duzia", fixed_factor=12)
    db.add(dozen)
    await db.commit()
    await db.refresh(dozen)
    with pytest.raises(SaleUnitInvalidError, match="fator de 1"):
        await create_sale_unit(db, company_id, product_id, box_id, 1, 125)
    with pytest.raises(SaleUnitInvalidError, match="contem sempre 12"):
        await create_sale_unit(db, company_id, product_id, dozen.id, 30, 3000)
    created = await create_sale_unit(db, company_id, product_id, dozen.id, 12, 1400)
    assert float(created.factor) == 12.0


@pytest.mark.asyncio
async def test_a_unit_dearer_than_the_base_needs_an_explicit_confirmation(db, company_with_essentials):
    company_id, product_id, egg_id, pallet_id, box_id = await _setup(db, company_with_essentials)
    with pytest.raises(SaleUnitNeedsConfirmationError) as excinfo:
        await create_sale_unit(db, company_id, product_id, box_id, 2, 3000)  # 1500 an egg, the egg alone is 125
    assert "mais caro que a unidade base" in excinfo.value.warnings[0]
    assert await list_sale_units(db, company_id, product_id) == []  # nothing saved
    confirmed = await create_sale_unit(db, company_id, product_id, box_id, 2, 3000, confirm=True)
    assert confirmed.is_active is True


@pytest.mark.asyncio
async def test_each_company_chooses_off_warn_or_block(db, company_with_essentials):
    company_id, product_id, egg_id, pallet_id, box_id = await _setup(db, company_with_essentials)
    await _set_check(db, company_id, "sale_unit_check_above_base", "block")
    with pytest.raises(SaleUnitInvalidError, match="mais caro"):
        await create_sale_unit(db, company_id, product_id, box_id, 2, 3000, confirm=True)
    await _set_check(db, company_id, "sale_unit_check_above_base", "off")
    unit = await create_sale_unit(db, company_id, product_id, box_id, 2, 3000)
    assert unit.is_active is True


@pytest.mark.asyncio
async def test_below_cost_and_same_factor_are_warned(db, company_with_essentials):
    company_id, product_id, egg_id, pallet_id, box_id = await _setup(db, company_with_essentials)
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
    product.purchase_price = 90
    await db.commit()
    with pytest.raises(SaleUnitNeedsConfirmationError) as excinfo:
        await create_sale_unit(db, company_id, product_id, pallet_id, 30, 500)  # 16.67 an egg, bought at 90
    assert "abaixo do custo" in excinfo.value.warnings[0]
    await create_sale_unit(db, company_id, product_id, pallet_id, 30, 3000)
    with pytest.raises(SaleUnitNeedsConfirmationError) as excinfo:
        await create_sale_unit(db, company_id, product_id, box_id, 30, 3000)
    assert "ja contem 30" in excinfo.value.warnings[0]
