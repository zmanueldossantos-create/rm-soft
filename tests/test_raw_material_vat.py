"""
Tests for raw materials without a VAT rate: allowed only for is_raw_material, every other product
still needs one (and an exemption reason at 0%), a raw material can never be sold (invoice / POS /
open account), and the response schema accepts a missing rate.
"""
import pytest

from app.main import app as fastapi_app
from app.schemas.product import ProductResponse
from app.services.cash_session_service import open_session
from app.services.open_account_service import ItemNotFoundError, add_line, open_account
from app.services.pos_service import checkout
from app.services.product_service import (
    ExemptionReasonRequiredError, create_product, update_product,
)
from app.services.service_service import ExemptionReasonRequiredError as ServiceExemptionReasonRequiredError


async def _create(db, ctx, code, vat_id, raw=False):
    return await create_product(
        db, company_id=ctx["company"].id, code=code, name="Item " + code, barcode=None, vat_id=vat_id,
        price=0 if raw else 1000, min_stock_threshold=0, expiry_date=None, is_sold_by_weight=False, is_raw_material=raw,
    )


@pytest.mark.asyncio
async def test_raw_material_needs_no_vat_and_no_exemption_reason(db, company_with_essentials):
    ctx = company_with_essentials
    without_vat = await _create(db, ctx, "MP-1", None, raw=True)
    assert without_vat.vat_id is None and without_vat.exemption_reason_id is None and without_vat.is_raw_material is True
    # even with a 0% rate given, a raw material never asks for an exemption reason
    exempt = await _create(db, ctx, "MP-3", ctx["vat_ise"].id, raw=True)
    assert exempt.exemption_reason_id is None


@pytest.mark.asyncio
async def test_a_normal_product_still_needs_a_vat_and_an_exemption_reason_at_zero(db, company_with_essentials):
    ctx = company_with_essentials
    with pytest.raises(ExemptionReasonRequiredError) as exc_info:
        await _create(db, ctx, "P-1", None)
    assert "Taxa de IVA" in str(exc_info.value)
    with pytest.raises(ExemptionReasonRequiredError):
        await _create(db, ctx, "P-2", ctx["vat_ise"].id)  # 0% without a reason: refused as before
    assert (await _create(db, ctx, "P-3", ctx["vat_nor"].id)).vat_id == ctx["vat_nor"].id


@pytest.mark.asyncio
async def test_update_can_make_a_raw_material_but_a_normal_product_keeps_needing_a_vat(db, company_with_essentials):
    ctx = company_with_essentials
    product = await _create(db, ctx, "P-4", ctx["vat_nor"].id)
    product_id = product.id
    common = dict(
        company_id=ctx["company"].id, product_id=product_id, code="P-4", name="Item P-4", barcode=None, price=1000,
        min_stock_threshold=0, expiry_date=None, is_sold_by_weight=False,
    )
    raw = await update_product(db, vat_id=None, is_raw_material=True, **common)
    assert raw.vat_id is None and raw.is_raw_material is True
    with pytest.raises(ExemptionReasonRequiredError):
        await update_product(db, vat_id=None, is_raw_material=False, **common)


@pytest.mark.asyncio
async def test_product_response_schema_accepts_a_missing_vat(db, company_with_essentials):
    ctx = company_with_essentials
    raw = await _create(db, ctx, "MP-5", None, raw=True)
    assert ProductResponse.model_validate(raw).vat_id is None


@pytest.mark.asyncio
async def test_invoice_and_pos_refuse_a_raw_material(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, pos_id, gestor, pm_id = ctx["company"].id, ctx["pos"].id, ctx["gestor"], ctx["pm_numerario"].id
    raw = await _create(db, ctx, "MP-6", None, raw=True)
    raw_id = raw.id
    await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    with pytest.raises(Exception) as exc_info:
        await checkout(
            db, company_id, pos_id, gestor, customer_id=None,
            lines_input=[{"product_id": raw_id, "quantity": 1}],
            payments=[{"payment_method_id": pm_id, "amount": 0.0}],
        )
    assert type(exc_info.value).__name__ == "ProductNotFoundError"
    assert "Materia-prima" in str(exc_info.value)


@pytest.mark.asyncio
async def test_open_account_refuses_a_raw_material(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, gestor_id = ctx["company"].id, ctx["gestor"].id
    raw = await _create(db, ctx, "MP-7", None, raw=True)
    raw_id = raw.id
    account = await open_account(db, company_id, ctx["activity"].id, ctx["pos"].id, gestor_id, "Mesa 1")
    with pytest.raises(ItemNotFoundError):
        await add_line(db, company_id, account.id, gestor_id, 1, product_id=raw_id)


def test_update_routes_answer_422_for_a_missing_vat_or_exemption_reason():
    """Only the create routes translated these errors: an update ended as a 500."""
    handlers = fastapi_app.exception_handlers
    assert ExemptionReasonRequiredError in handlers
    assert ServiceExemptionReasonRequiredError in handlers