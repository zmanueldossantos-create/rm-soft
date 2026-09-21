"""Closing an open account: the document type is not imposed by the request, the catalog decides."""
from app.schemas.open_account import OpenAccountCloseRequest


def test_close_request_leaves_the_type_to_the_catalog():
    assert OpenAccountCloseRequest().invoice_type is None
    assert OpenAccountCloseRequest(invoice_type="FACTURA").invoice_type == "FACTURA"  # an explicit choice is still honoured