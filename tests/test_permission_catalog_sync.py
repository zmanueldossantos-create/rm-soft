"""An existing permission follows the catalog: renamed or moved to another category, it is updated at the next sync."""
import pytest

from app.services.permission_service import PERMISSION_CATALOG, _ensure_catalog

CODE = "tesouraria:associations_manage"


@pytest.mark.asyncio
async def test_existing_permissions_follow_the_catalog_label_and_category(db):
    expected = next(e for e in PERMISSION_CATALOG if e[0] == CODE)
    assert expected[2] == "Atividades"  # the association is managed where the cash points are created

    permission = (await _ensure_catalog(db))[CODE]
    permission.label, permission.category = "Etiqueta antiga", "Tesouraria"
    await db.commit()

    synced = (await _ensure_catalog(db))[CODE]
    await db.commit()
    await db.refresh(synced)
    assert (synced.label, synced.category) == (expected[1], expected[2])