"""Editing the activity's default cash point is refused with a 409 and the service's message - not a 500."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.activities import routes
from app.services.point_of_sale_service import DefaultPosNotModifiableError


@pytest.mark.asyncio
async def test_editing_the_default_pos_answers_409(monkeypatch):
    async def refuse(*args, **kwargs):
        raise DefaultPosNotModifiableError("A caixa por defeito da atividade nao pode ser renomeada")

    monkeypatch.setattr(routes, "update_point_of_sale", refuse)
    with pytest.raises(HTTPException) as refused:
        await routes.edit_pos(
            pos_id=uuid.uuid4(), payload=SimpleNamespace(name="x", billetage_enabled=False),
            db=None, current_user=SimpleNamespace(company_id=uuid.uuid4()),
        )
    assert refused.value.status_code == 409
    assert "por defeito" in refused.value.detail