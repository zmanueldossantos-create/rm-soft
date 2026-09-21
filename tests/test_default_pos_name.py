"""Default cash points are all named "Caixa Geral"; the response tells the screen which one is the default."""
import glob
import importlib.util
import pathlib

import pytest
from sqlalchemy import text

from app.models.point_of_sale import PointOfSale
from app.schemas.pos import PointOfSaleResponse
from app.services.point_of_sale_service import DEFAULT_POS_NAME


def _rename_sql() -> str:
    path = glob.glob(str(pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions" / "m9c6d2f57a41_*.py"))[0]
    spec = importlib.util.spec_from_file_location("default_pos_name_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RENAME_SQL


async def _set(db, pos_id, name, is_default):
    await db.execute(text(f"UPDATE {PointOfSale.__tablename__} SET name = :n, is_default = :d WHERE id = :i"),
                     {"n": name, "d": is_default, "i": pos_id})
    await db.commit()


async def _name(db, pos_id):
    return (await db.execute(text(f"SELECT name FROM {PointOfSale.__tablename__} WHERE id = :i"), {"i": pos_id})).scalar_one()


def test_the_name_constant_and_the_response_field():
    assert DEFAULT_POS_NAME == "Caixa Geral"
    assert "is_default" in PointOfSaleResponse.model_fields


@pytest.mark.asyncio
async def test_default_cash_points_are_renamed_and_the_others_are_not(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id = ctx["company"].id, ctx["activity"].id, ctx["pos"].id
    other = PointOfSale(company_id=company_id, activity_id=activity_id, name="CAIXA 2", is_default=False, billetage_enabled=False)
    db.add(other)
    await db.commit()
    await db.refresh(other)
    other_id = other.id

    await _set(db, pos_id, "Servicos - Caixa Geral", True)
    await db.execute(text(_rename_sql()))
    await db.commit()
    assert await _name(db, pos_id) == "Caixa Geral"
    assert await _name(db, other_id) == "CAIXA 2"  # not a default cash point: untouched


@pytest.mark.asyncio
async def test_a_default_is_not_renamed_when_the_activity_already_has_that_name(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id = ctx["company"].id, ctx["activity"].id, ctx["pos"].id
    taken = PointOfSale(company_id=company_id, activity_id=activity_id, name="Caixa Geral", is_default=False, billetage_enabled=False)
    db.add(taken)
    await db.commit()

    await _set(db, pos_id, "Servicos - Caixa Geral", True)
    await db.execute(text(_rename_sql()))
    await db.commit()
    assert await _name(db, pos_id) == "Servicos - Caixa Geral"  # no duplicate name inside one activity