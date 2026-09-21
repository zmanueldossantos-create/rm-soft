"""The rules of the document types are readable by any signed-in user (read only), not only by those who manage catalogs."""
from app.api.v1.catalogs.routes import router


def test_rules_route_is_read_only_and_needs_only_a_signed_in_user():
    routes = [r for r in router.routes if r.path.endswith("/document-rules")]
    assert len(routes) == 1 and routes[0].methods == {"GET"}
    called = {getattr(d.call, "__name__", "") for d in routes[0].dependant.dependencies}
    assert "get_current_user" in called