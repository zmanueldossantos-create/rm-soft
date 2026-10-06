"""Point 33 - le serveur prend les commandes sur les contas abertas, sans jamais encaisser."""
from app.models.user import UserRole
from app.services.permission_service import EDITABLE_ROLES, PERMISSION_CATALOG

ROLE = "ATENDENTE"
DEFAULTS = {code: roles for code, _, _, roles in PERMISSION_CATALOG}
WAITER = {code for code, roles in DEFAULTS.items() if ROLE in roles}


def test_role_exists_and_is_editable_in_the_matrix() -> None:
    assert UserRole(ROLE).value == ROLE
    assert ROLE in EDITABLE_ROLES


def test_waiter_takes_orders_on_open_accounts() -> None:
    for code in ("open_accounts:view", "open_accounts:open", "open_accounts:edit_lines", "open_accounts:transfer"):
        assert code in WAITER, code


def test_waiter_never_closes_nor_cashes() -> None:
    assert "open_accounts:close" not in WAITER
    assert not {c for c in WAITER if c.startswith(("pos:", "moedeiro:", "invoices:", "documents:"))}


def test_cashier_keeps_every_open_account_right() -> None:
    for code in ("open_accounts:view", "open_accounts:open", "open_accounts:edit_lines",
                 "open_accounts:transfer", "open_accounts:close"):
        assert "CAIXA" in DEFAULTS[code], code
