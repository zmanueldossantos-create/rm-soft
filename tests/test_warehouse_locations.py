"""
Emplacements (point 5): a warehouse may have places (optional - none at first: everything works as before), a product
is kept in one place per warehouse, shown next to its stock, its lots and on the inventory, which is then sorted by
place. A place still holding products cannot be deactivated; a product is never put in another warehouse's place.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.services.location_service import (
    LocationError, create_location, list_locations, set_product_location, toggle_location, update_location,
)
from app.services.stock_inventory_service import create_inventory, get_inventory
from app.services.stock_lot_service import list_lots
from app.services.stock_service import list_stock_levels, receive_stock


async def _products(db, ctx, *names, followed=False):
    ids = []
    for name in names:
        product = Product(company_id=ctx["company"].id, code=name[:3].upper() + uuid.uuid4().hex[:4], name=name,
                          vat_id=ctx["vat_nor"].id, price=100, min_stock_threshold=0, product_type=ProductType.BEM,
                          unit_of_measure_id=ctx["unit_un"].id, managed_by_expiry=followed)
        db.add(product)
        await db.flush()
        ids.append(product.id)
    await db.commit()
    return ids


@pytest.mark.asyncio
async def test_places_are_optional_then_shown_and_sort_the_inventory(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id, central, shop = ctx["company"].id, ctx["gestor"].id, ctx["central_warehouse"].id, ctx["activity_warehouse"].id
    apple, butter, cheese = await _products(db, ctx, "Ananás", "Manteiga", "Queijo")
    for product_id in (apple, butter, cheese):
        db.add(Stock(company_id=company_id, product_id=product_id, warehouse_id=central, quantity=5))
    await db.commit()
    levels = await list_stock_levels(db, company_id, central)
    assert {l["location_code"] for l in levels} == {None}  # no place yet: nothing changes

    fridge = await create_location(db, company_id, central, " frigo 1 ", "Câmara fria")
    shelf = await create_location(db, company_id, central, "A-01")
    with pytest.raises(LocationError, match="Já existe a localização FRIGO 1"):
        await create_location(db, company_id, central, "FRIGO 1")
    other = await create_location(db, company_id, shop, "BALCAO")
    with pytest.raises(LocationError, match="outro armazém"):
        await set_product_location(db, company_id, cheese, central, other.id)

    await set_product_location(db, company_id, butter, central, fridge.id)
    await set_product_location(db, company_id, cheese, central, fridge.id)
    await set_product_location(db, company_id, apple, central, shelf.id)
    levels = {l["product_id"]: l["location_code"] for l in await list_stock_levels(db, company_id, central)}
    assert (levels[apple], levels[butter], levels[cheese]) == ("A-01", "FRIGO 1 · Câmara fria", "FRIGO 1 · Câmara fria")
    assert {l["code"]: l["products"] for l in await list_locations(db, company_id, central)} == {"A-01": 1, "FRIGO 1": 2}

    with pytest.raises(LocationError, match="usada por 2 produto"):
        await toggle_location(db, company_id, fridge.id)
    await set_product_location(db, company_id, cheese, central, None)  # no longer kept anywhere in particular
    await update_location(db, company_id, fridge.id, "F-01", "Câmara fria")

    inventory = await create_inventory(db, company_id, central, user_id)
    lines = (await get_inventory(db, company_id, inventory.id))["lines"]
    assert [(l["name"], l["location_code"]) for l in lines] == [("Ananás", "A-01"), ("Manteiga", "F-01 · Câmara fria"), ("Queijo", None)]


@pytest.mark.asyncio
async def test_the_lots_show_where_they_are(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, central = ctx["company"].id, ctx["central_warehouse"].id
    (yogurt,) = await _products(db, ctx, "Iogurte", followed=True)
    await receive_stock(db, company_id, yogurt, 4, expiry_date=date.today() + timedelta(days=9))
    place = await create_location(db, company_id, central, "F-02")
    await set_product_location(db, company_id, yogurt, central, place.id)
    assert [l["location_code"] for l in await list_lots(db, company_id, yogurt)] == ["F-02"]
    await toggle_location(db, company_id, (await create_location(db, company_id, central, "OLD")).id)  # unused: off
    with pytest.raises(LocationError, match="está desativada"):
        old = next(l for l in await list_locations(db, company_id, central) if l["code"] == "OLD")
        await set_product_location(db, company_id, yogurt, central, old["id"])
