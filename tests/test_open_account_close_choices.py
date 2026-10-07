"""Point 3 - closing an account at the till takes the choices of a direct sale."""
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.open_account import OpenAccountCloseRequest


def test_closing_takes_customer_discount_and_payment_term():
    request = OpenAccountCloseRequest()
    assert (request.customer_id, request.discount_global_percent, request.payment_term_id) == (None, 0, None)
    customer, term = uuid.uuid4(), uuid.uuid4()
    request = OpenAccountCloseRequest(invoice_type="FACTURA", customer_id=customer, discount_global_percent=10, payment_term_id=term)
    assert (request.customer_id, request.discount_global_percent, request.payment_term_id) == (customer, 10, term)
    with pytest.raises(ValidationError):
        OpenAccountCloseRequest(discount_global_percent=120)
