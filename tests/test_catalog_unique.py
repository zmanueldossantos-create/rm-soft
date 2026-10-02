"""Catalogs refuse duplicates whatever the case (unique indexes on lower(...))."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.bank import Bank


@pytest.mark.asyncio
async def test_a_bank_acronym_is_unique_whatever_the_case(db):
    db.add(Bank(acronym="TSTU", full_name="Banco Teste Unico"))
    await db.commit()
    db.add(Bank(acronym="tstu", full_name="Banco Teste Repetido"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
