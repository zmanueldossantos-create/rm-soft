"""Hotel point 2, part D: a resource type keeps the usual entry / exit hours of its bookings (a room: 14:00 -> 12:00
the next day), proposed by the booking form. Both or neither."""
from datetime import time

import pytest
from pydantic import ValidationError

from app.schemas.booking import ResourceTypeCreateRequest, ResourceTypeResponse, ResourceTypeUpdateRequest
from app.services.resource_type_service import create_resource_type, update_resource_type


@pytest.mark.asyncio
async def test_a_room_type_keeps_its_entry_and_exit_hours(db, company_with_essentials):
    cid = company_with_essentials["company"].id
    room = await create_resource_type(db, cid, "Quarto", True, time(14, 0), time(12, 0))
    response = ResourceTypeResponse.model_validate(room)
    assert (response.default_start_time, response.default_end_time) == (time(14, 0), time(12, 0))
    # a full edit without hours leaves the type without hours
    room = await update_resource_type(db, cid, room.id, "Quarto", True)
    assert room.default_start_time is None and room.default_end_time is None


@pytest.mark.asyncio
async def test_a_table_type_has_no_hours(db, company_with_essentials):
    table = await create_resource_type(db, company_with_essentials["company"].id, "Mesa")
    assert table.default_start_time is None and table.default_end_time is None


def test_the_hours_go_together():
    with pytest.raises(ValidationError, match="nenhuma"):
        ResourceTypeCreateRequest(name="Quarto", default_start_time="14:00")
    with pytest.raises(ValidationError, match="nenhuma"):
        ResourceTypeUpdateRequest(name="Quarto", default_end_time="12:00")
    both = ResourceTypeCreateRequest(name="Quarto", requires_service=True, default_start_time="14:00", default_end_time="12:00")
    assert both.default_end_time == time(12, 0)
