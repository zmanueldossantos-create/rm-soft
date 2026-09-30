"""Request validation errors answered in Portuguese, naming the field and the line."""
import json

import pytest
from fastapi.exceptions import RequestValidationError

from app.main import _pt_validation_handler


async def _messages(errors):
    response = await _pt_validation_handler(None, RequestValidationError(errors))
    assert response.status_code == 422
    return [e["msg"] for e in json.loads(response.body)["detail"]]


@pytest.mark.asyncio
async def test_a_bad_quantity_on_a_line_names_the_line_and_the_field():
    msgs = await _messages([{"type": "float_parsing", "loc": ("body", "lines", 0, "quantity"), "msg": "Input should be a valid number", "input": "1,"}])
    assert msgs == ["Linha 1 - Quantidade: valor numerico invalido"]


@pytest.mark.asyncio
async def test_bounds_and_our_own_messages():
    msgs = await _messages([
        {"type": "greater_than", "loc": ("body", "factor"), "msg": "Input should be greater than 0", "ctx": {"gt": 0}},
        {"type": "value_error", "loc": ("body", "price"), "msg": "Value error, O preco nao pode ser negativo"},
    ])
    assert msgs == ["Fator: deve ser maior que 0", "Value error, O preco nao pode ser negativo"]
