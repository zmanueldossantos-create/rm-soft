"""products:manage moved from CORE to the STOCK capability - a sector without STOCK (Servicos) never gets it,
one with STOCK (Comercio) does; services:manage stays CORE, available to every sector regardless."""
from app.core.capabilities import CORE, capability_of_permission


def test_products_is_now_under_stock_not_core():
    assert capability_of_permission("products:manage") == "STOCK"
    assert capability_of_permission("services:manage") == CORE


def test_products_capability_paths_include_the_screens():
    from app.core.capabilities import CAPABILITIES
    stock = CAPABILITIES["STOCK"]
    assert "/products" in stock.screens
    assert "/materia-prima" in stock.screens