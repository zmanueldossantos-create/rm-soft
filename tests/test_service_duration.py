"""
Tests for Service.duration_minutes - the optional default length of a booking for a service
(massage 60 min, haircut 30 min...). The reservation form uses it to fill in the end time.
"""
import pytest
from pydantic import ValidationError

from app.schemas.service import ServiceCreateRequest, ServiceResponse
from app.services.service_service import create_service, update_service


async def _create(db, ctx, code, name, **extra):
    return await create_service(
        db, company_id=ctx["company"].id, unit_of_measure_id=ctx["unit_un"].id, code=code, name=name, vat_id=ctx["vat_nor"].id, price=1000, **extra,
    )


@pytest.mark.asyncio
async def test_duration_is_stored(db, company_with_essentials):
    service = await _create(db, company_with_essentials, "MAS-60", "Massagem 60min", duration_minutes=60)
    assert service.duration_minutes == 60
    assert "duration_minutes" in ServiceResponse.model_fields


@pytest.mark.asyncio
async def test_duration_is_optional(db, company_with_essentials):
    service = await _create(db, company_with_essentials, "LAV-1", "Lavandaria por Peca")
    assert service.duration_minutes is None


@pytest.mark.asyncio
async def test_update_changes_and_clears_the_duration(db, company_with_essentials):
    ctx = company_with_essentials
    service = await _create(db, ctx, "COR-30", "Corte", duration_minutes=30)
    service_id = service.id
    common = dict(unit_of_measure_id=ctx["unit_un"].id, company_id=ctx["company"].id, service_id=service_id, code="COR-30", name="Corte", vat_id=ctx["vat_nor"].id, price=1000)

    changed = await update_service(db, duration_minutes=45, **common)
    assert changed.duration_minutes == 45

    cleared = await update_service(db, duration_minutes=None, **common)
    assert cleared.duration_minutes is None


def test_schema_rejects_out_of_range_durations_and_accepts_none():
    base = dict(code="X-1", name="Servico", vat_id="11111111-1111-4111-8111-111111111111")
    for bad in (0, 4, 1441, -30):
        with pytest.raises(ValidationError):
            ServiceCreateRequest(duration_minutes=bad, **base)
    assert ServiceCreateRequest(**base).duration_minutes is None
    assert ServiceCreateRequest(duration_minutes=5, **base).duration_minutes == 5
    assert ServiceCreateRequest(duration_minutes=1440, **base).duration_minutes == 1440
