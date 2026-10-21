"""
Cópias de segurança automáticas / manuais: the gestor chooses automatic (1 to 3 hours a day, Luanda) or manual;
«Fazer cópia agora» writes the complete export file in the company's folder (never under /uploads); the gestor
downloads only its company's copies; old copies are cleared (7 days, then one per week for 4 weeks); the automatic
copies due are made one company after another, each only once.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.company_backup import CompanyBackup, CompanyBackupSettings
from app.services.company_backup_jobs import (BackupSettingsError, company_dir, make_backup, next_run, prune,
                                              run_due_backups, save_backup_settings)
from app.services.permission_service import seed_permission_catalog


@pytest.fixture(autouse=True)
def backup_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "BACKUP_DIR", str(tmp_path / "backups"))
    return tmp_path / "backups"


def test_the_next_hour_in_luanda():
    after = datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)  # 13:30 in Luanda
    assert next_run(["13:00", "18:00"], after) == datetime(2026, 10, 21, 17, 0, tzinfo=timezone.utc)
    assert next_run(["08:00"], after) == datetime(2026, 10, 22, 7, 0, tzinfo=timezone.utc)  # tomorrow
    assert next_run([], after) is None


async def test_settings_are_checked(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    for mode, times, message in (("AUTOMATICA", [], "pelo menos uma hora"), ("AUTOMATICA", ["25:00"], "inválida"),
                                 ("AUTOMATICA", ["08:00", "12:00", "18:00", "23:00"], "No máximo 3"),
                                 ("SEMPRE", ["08:00"], "Automática")):
        with pytest.raises(BackupSettingsError, match=message):
            await save_backup_settings(db, company_id, mode, times)
    row = await save_backup_settings(db, company_id, "AUTOMATICA", ["23:30", "13:00", "13:00"])
    assert row.times == ["13:00", "23:30"] and row.next_run_at is not None
    row = await save_backup_settings(db, company_id, "MANUAL", row.times)
    assert row.times == ["13:00", "23:30"] and row.next_run_at is None  # the hours stay, nothing automatic


async def test_a_copy_now_and_its_download_by_the_gestor_only(db, company_with_essentials, backup_dir):
    ctx = company_with_essentials
    await seed_permission_catalog(db)
    copy = await make_backup(db, ctx["company"].id, "MANUAL", ctx["gestor"].id)
    assert copy.status == "FEITA" and copy.size_bytes > 0
    path = company_dir(ctx["company"].id) / copy.file_name
    assert path.is_file() and path.parent.parent == backup_dir and "uploads" not in str(path)

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            gestor = {"Authorization": "Bearer " + create_access_token(
                subject=str(ctx["gestor"].id), company_id=str(ctx["company"].id), role="GESTOR")}
            listed = (await client.get("/api/v1/company/me/backups", headers=gestor)).json()
            assert listed["settings"]["mode"] == "MANUAL" and listed["copies"][0]["id"] == str(copy.id)
            got = await client.get(f"/api/v1/company/me/backups/{copy.id}/download", headers=gestor)
            assert got.status_code == 200 and got.content == path.read_bytes()
            made = await client.post("/api/v1/company/me/backups", headers=gestor)
            assert made.status_code == 200 and made.json()["kind"] == "MANUAL"
            saved = await client.put("/api/v1/company/me/backups/settings", json={"mode": "AUTOMATICA", "times": ["99:00"]}, headers=gestor)
            assert saved.status_code == 422 and "inválida" in saved.json()["detail"]
            # another company's copy: not found for this gestor
            other = CompanyBackup(company_id=ctx["company"].id, kind="MANUAL", status="FEITA", file_name=copy.file_name)
            from app.models.company import Company
            stranger = Company(name="Outra Lda", nif="5999999991", email="o@o.ao", phone_number="+244923999555")
            db.add(stranger)
            await db.flush()
            other.company_id = stranger.id
            db.add(other)
            await db.commit()
            assert (await client.get(f"/api/v1/company/me/backups/{other.id}/download", headers=gestor)).status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_old_copies_are_cleared(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    folder = company_dir(company_id)
    folder.mkdir(parents=True, exist_ok=True)
    ages = [1, 3, 6, 8, 9, 10, 16, 17, 25, 33, 34, 40, 60]  # days ago, one copy each
    for days in ages:
        name = f"copia_{days}.zip"
        (folder / name).write_bytes(b"x")
        db.add(CompanyBackup(company_id=company_id, kind="AUTOMATICA", status="FEITA", file_name=name,
                             created_at=now - timedelta(days=days)))
    db.add(CompanyBackup(company_id=company_id, kind="AUTOMATICA", status="ERRO", error="disco cheio",
                         created_at=now - timedelta(days=9)))
    await db.commit()
    await prune(db, company_id, now)
    kept = sorted(int(r.file_name.split("_")[1].split(".")[0]) for r in (await db.execute(
        select(CompanyBackup).where(CompanyBackup.company_id == company_id))).scalars() if r.file_name)
    # the 7 last days all; then the newest of each week, up to 35 days
    assert kept[:3] == [1, 3, 6] and 40 not in kept and 60 not in kept and len(kept) <= 3 + 5
    assert all((folder / f"copia_{d}.zip").exists() == (d in kept) for d in ages)
    assert not (await db.execute(select(CompanyBackup).where(CompanyBackup.status == "ERRO"))).scalars().all()


async def test_the_automatic_copies_due_are_made_once(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await save_backup_settings(db, company_id, "AUTOMATICA", ["13:00"])
    row = (await db.execute(select(CompanyBackupSettings).where(CompanyBackupSettings.company_id == company_id))).scalar_one()
    row.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()
    assert await run_due_backups(db) == 1
    assert await run_due_backups(db) == 0  # its next hour is set: not again
    await db.refresh(row)
    assert row.next_run_at > datetime.now(timezone.utc)
    [copy] = (await db.execute(select(CompanyBackup).where(CompanyBackup.company_id == company_id))).scalars().all()
    assert (copy.kind, copy.status) == ("AUTOMATICA", "FEITA")
