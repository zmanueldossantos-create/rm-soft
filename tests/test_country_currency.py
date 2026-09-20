"""
Tests for Country.default_currency_id in the countries API response: the customer form pre-fills its
"Moeda" from it, and the API used to leave the field out (so the currency was always saved empty).
"""
import uuid
from types import SimpleNamespace

from app.models.country import Country
from app.schemas.catalog import CountryResponse


def test_country_response_exposes_the_default_currency():
    assert "default_currency_id" in CountryResponse.model_fields
    currency_id = uuid.uuid4()
    country = SimpleNamespace(id=uuid.uuid4(), code="AO", name="Angola", is_active=True, default_currency_id=currency_id)
    assert CountryResponse.model_validate(country).default_currency_id == currency_id


def test_country_response_accepts_a_country_without_a_default_currency():
    country = SimpleNamespace(id=uuid.uuid4(), code="XX", name="Sem moeda", is_active=True, default_currency_id=None)
    assert CountryResponse.model_validate(country).default_currency_id is None


def test_country_model_keeps_the_default_currency_column():
    assert hasattr(Country, "default_currency_id")