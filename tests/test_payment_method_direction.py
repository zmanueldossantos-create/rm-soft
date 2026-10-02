"""A payment method is checked by the direction of the money: allows_receipt for money in, allows_payment for money out."""
import uuid

import pytest

from app.models.payment_method_catalog import PaymentMethodCatalog
from app.services.invoice_service import PaymentMethodNotAllowedError, _ensure_methods_allowed


async def _method(db, allows_payment, allows_receipt):
    method = PaymentMethodCatalog(code="T" + uuid.uuid4().hex[:3].upper(), name="Metodo teste",
                                  allows_payment=allows_payment, allows_receipt=allows_receipt)
    db.add(method)
    await db.commit()
    await db.refresh(method)
    return method


@pytest.mark.asyncio
async def test_a_method_that_cannot_receive_is_refused_for_money_in(db):
    method = await _method(db, allows_payment=True, allows_receipt=False)
    with pytest.raises(PaymentMethodNotAllowedError, match="recebimentos"):
        await _ensure_methods_allowed(db, [method.id], "in")
    await _ensure_methods_allowed(db, [method.id], "out")  # paying out is allowed


@pytest.mark.asyncio
async def test_a_method_that_cannot_pay_is_refused_for_money_out(db):
    method = await _method(db, allows_payment=False, allows_receipt=True)
    with pytest.raises(PaymentMethodNotAllowedError, match="pagamentos ou devolucoes"):
        await _ensure_methods_allowed(db, [method.id], "out")
    await _ensure_methods_allowed(db, [method.id], "in")  # receiving is allowed
