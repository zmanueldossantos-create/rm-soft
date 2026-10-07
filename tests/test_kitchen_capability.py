"""The kitchen is a capability of its own: the Restaurante has it, the Bar (now with tables) and the Hotel do not."""
from app.core.capabilities import CAPABILITIES, SECTORS_BY_CODE, capability_of_permission, expand_dependencies


def test_the_kitchen_is_its_own_capability_and_needs_open_accounts():
    assert capability_of_permission("kitchen:view") == capability_of_permission("kitchen:history") == "KITCHEN"
    assert CAPABILITIES["KITCHEN"].requires == ("OPEN_ACCOUNTS",)
    assert "OPEN_ACCOUNTS" in expand_dependencies({"KITCHEN"})
    assert "/cozinha" not in CAPABILITIES["OPEN_ACCOUNTS"].screens


def test_the_restaurant_cooks_the_bar_has_tables_the_hotel_takes_the_restaurant_for_its_kitchen():
    assert "KITCHEN" in SECTORS_BY_CODE["RESTAURANTE"].capabilities
    assert "KITCHEN" not in SECTORS_BY_CODE["BAR"].capabilities
    assert "RESOURCES" in SECTORS_BY_CODE["BAR"].capabilities
    assert "KITCHEN" not in SECTORS_BY_CODE["HOTEL"].capabilities
