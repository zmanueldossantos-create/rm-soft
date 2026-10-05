"""A company never has two VAT rates of one tax code - not even created by hand."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.vat import VAT


@pytest.mark.asyncio
async def test_a_second_rate_of_the_same_code_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    db.add(VAT(company_id=ctx["company"].id, name="Outra taxa normal", rate=12, tax_category="NOR", is_active=True))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
