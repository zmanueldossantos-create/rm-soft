"""requires_payment_term is a plain document type rule column, exposed by the catalog schema."""
from app.models.document_type import DocumentType
from app.schemas.catalog import DocumentTypeResponse


def test_column_exists_and_defaults_to_false():
    column = DocumentType.__table__.c.requires_payment_term
    assert column.type.python_type is bool
    assert column.default.arg is False


def test_schema_exposes_the_field():
    assert "requires_payment_term" in DocumentTypeResponse.model_fields