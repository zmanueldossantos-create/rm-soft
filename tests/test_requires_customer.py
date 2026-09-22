"""requires_customer is a plain document type rule column, exposed by the catalog schema, defaulting to True for FT only."""
from app.models.document_type import DocumentType
from app.schemas.catalog import DocumentTypeResponse


def test_column_exists_and_defaults_to_false():
    column = DocumentType.__table__.c.requires_customer
    assert column.type.python_type is bool
    assert column.default.arg is False


def test_schema_exposes_the_field():
    assert "requires_customer" in DocumentTypeResponse.model_fields