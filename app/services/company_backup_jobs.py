"""
Cópias de segurança de uma empresa - automatic (1 to 3 hours a day, chosen by its gestor) or manual («Fazer cópia
agora»). Each copy is the full file of «Exportar» (company_backup_service), kept on the server in
BACKUP_DIR/<company id>/, outside the web-served /uploads. The gestor downloads its company's copies; only the
platform restores.

Kept: every copy of the last 7 days, then the newest copy of each of the 4 weeks before; older ones are deleted, file
and record (a failed attempt is kept 7 days, to be seen).

The backend runs the automatic copies itself (backup_loop, started with the application - local and SaaS alike), one
company after another: a company due is claimed with its row locked (FOR UPDATE SKIP LOCKED), so two server processes
never copy the same company twice.
"""
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.company import Company
from app.models.company_backup import CompanyBackup, CompanyBackupSettings
from app.services.company_backup_service import export_company

log = logging.getLogger(__name__)
LUANDA = timezone(timedelta(hours=1))  # Angola: UTC+1 all year
MAX_TIMES = 3
KEEP_DAYS = 7
KEEP_WEEKS = 4
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class BackupSettingsError(Exception):
    """Raised when the backup settings are refused (an hour badly written, more than 3 a day...)."""


def company_dir(company_id: uuid.UUID) -> Path:
    return Path(get_settings().BACKUP_DIR) / str(company_id)


def next_run(times: list[str], after: datetime) -> datetime | None:
    """The next of these Luanda hours after this moment (today, else tomorrow), as a UTC moment."""
    if not times:
        return None
    local = after.astimezone(LUANDA)
    candidates = []
    for day in (local.date(), local.date() + timedelta(days=1)):
        for value in times:
            hour, minute = (int(x) for x in value.split(":"))
            moment = datetime.combine(day, time(hour, minute), tzinfo=LUANDA)
            if moment > local:
                candidates.append(moment)
    return min(candidates).astimezone(timezone.utc)


async def get_backup_settings(db: AsyncSession, company_id: uuid.UUID) -> CompanyBackupSettings:
    """The company's settings - manual until its gestor chooses (no row yet: manual, no hour)."""
    row = (await db.execute(select(CompanyBackupSettings).where(CompanyBackupSettings.company_id == company_id))).scalar_one_or_none()
    return row or CompanyBackupSettings(company_id=company_id, mode="MANUAL", times=[], next_run_at=None)


async def save_backup_settings(db: AsyncSession, company_id: uuid.UUID, mode: str, times: list[str]) -> CompanyBackupSettings:
    """Automatic at 1 to 3 hours a day (Luanda), or manual only - the hours chosen are kept either way."""
    if mode not in ("AUTOMATICA", "MANUAL"):
        raise BackupSettingsError("Escolha «Automática» ou «Manual»")
    clean = sorted({t.strip() for t in times if t and t.strip()})
    bad = [t for t in clean if not _TIME.match(t)]
    if bad:
        raise BackupSettingsError(f"Hora inválida: {bad[0]} (formato HH:MM)")
    if len(clean) > MAX_TIMES:
        raise BackupSettingsError(f"No máximo {MAX_TIMES} cópias automáticas por dia")
    if mode == "AUTOMATICA" and not clean:
        raise BackupSettingsError("Escolha pelo menos uma hora para a cópia automática")
    row = (await db.execute(select(CompanyBackupSettings).where(CompanyBackupSettings.company_id == company_id))).scalar_one_or_none()
    if row is None:
        row = CompanyBackupSettings(company_id=company_id)
        db.add(row)
    row.mode, row.times = mode, clean
    row.next_run_at = next_run(clean, datetime.now(timezone.utc)) if mode == "AUTOMATICA" else None
    await db.commit()
    await db.refresh(row)
    return row


async def make_backup(db: AsyncSession, company_id: uuid.UUID, kind: str,
                      user_id: uuid.UUID | None = None) -> CompanyBackup:
    """One copy now: the file written in the company's folder (complete, or nothing), recorded FEITA - or ERRO with
    its reason. Then the old copies are cleared."""
    record = CompanyBackup(company_id=company_id, kind=kind, created_by_user_id=user_id)
    try:
        content, filename = await export_company(db, company_id)
        folder = company_dir(company_id)
        folder.mkdir(parents=True, exist_ok=True)
        partial = folder / (filename + ".part")
        partial.write_bytes(content)
        os.replace(partial, folder / filename)  # never a half-written copy under its real name
        record.status, record.file_name, record.size_bytes = "FEITA", filename, len(content)
    except Exception as e:  # noqa: BLE001 - a failed copy is recorded, never lost silently
        await db.rollback()
        log.exception("backup of company %s failed", company_id)
        record.status, record.error = "ERRO", (str(e) or e.__class__.__name__)[:500]
    db.add(record)
    await db.commit()
    await prune(db, company_id)
    await db.refresh(record)
    return record


async def prune(db: AsyncSession, company_id: uuid.UUID, now: datetime | None = None) -> int:
    """Clears the old copies: all of the last 7 days stay, then the newest of each of the 4 weeks before."""
    now = now or datetime.now(timezone.utc)
    rows = (await db.execute(select(CompanyBackup).where(CompanyBackup.company_id == company_id)
                             .order_by(CompanyBackup.created_at.desc()))).scalars().all()
    weeks_kept: set = set()
    gone = []
    for row in rows:
        age = now - row.created_at
        if age <= timedelta(days=KEEP_DAYS):
            continue
        if row.status == "FEITA" and age <= timedelta(days=KEEP_DAYS + 7 * KEEP_WEEKS):
            week = row.created_at.astimezone(LUANDA).isocalendar()[:2]
            if week not in weeks_kept:
                weeks_kept.add(week)
                continue
        gone.append(row)
    for row in gone:
        if row.file_name:
            (company_dir(company_id) / row.file_name).unlink(missing_ok=True)
    if gone:
        await db.execute(delete(CompanyBackup).where(CompanyBackup.id.in_([r.id for r in gone])))
        await db.commit()
    return len(gone)


def backup_view(row: CompanyBackup) -> dict:
    return {"id": row.id, "kind": row.kind, "status": row.status, "file_name": row.file_name,
            "size_bytes": row.size_bytes, "error": row.error, "created_at": row.created_at}


def settings_view(row: CompanyBackupSettings) -> dict:
    return {"mode": row.mode, "times": row.times or [], "next_run_at": row.next_run_at, "max_times": MAX_TIMES,
            "keep_days": KEEP_DAYS, "keep_weeks": KEEP_WEEKS}


async def list_backups(db: AsyncSession, company_id: uuid.UUID) -> list[CompanyBackup]:
    return (await db.execute(select(CompanyBackup).where(CompanyBackup.company_id == company_id)
                             .order_by(CompanyBackup.created_at.desc()))).scalars().all()


async def backup_file(db: AsyncSession, company_id: uuid.UUID | None, backup_id: uuid.UUID) -> tuple[Path, str]:
    """A copy's file - of this company only (company_id None: the platform, any company)."""
    row = await db.get(CompanyBackup, backup_id)
    if row is None or (company_id is not None and row.company_id != company_id) or not row.file_name:
        raise BackupSettingsError("Cópia não encontrada")
    path = company_dir(row.company_id) / row.file_name
    if not path.is_file():
        raise BackupSettingsError("O ficheiro desta cópia já não existe no servidor")
    return path, row.file_name


async def backups_overview(db: AsyncSession) -> list[dict]:
    """The platform's view: each company's settings, last copy, failures and space used."""
    companies = (await db.execute(select(Company).order_by(Company.name))).scalars().all()
    settings = {s.company_id: s for s in (await db.execute(select(CompanyBackupSettings))).scalars().all()}
    stats = {r.company_id: r for r in (await db.execute(
        select(CompanyBackup.company_id, func.count().label("copies"), func.coalesce(func.sum(CompanyBackup.size_bytes), 0).label("size"),
               func.max(CompanyBackup.created_at).filter(CompanyBackup.status == "FEITA").label("last_ok"))
        .group_by(CompanyBackup.company_id))).all()}
    last = {}
    for row in (await db.execute(select(CompanyBackup).order_by(CompanyBackup.created_at.desc()))).scalars().all():
        last.setdefault(row.company_id, row)
    now = datetime.now(timezone.utc)
    result = []
    for company in companies:
        s, st, lt = settings.get(company.id), stats.get(company.id), last.get(company.id)
        last_ok = st.last_ok if st else None
        result.append({
            "company_id": company.id, "name": company.short_name or company.name, "nif": company.nif,
            "is_active": company.is_active, "mode": s.mode if s else "MANUAL", "times": s.times if s else [],
            "next_run_at": s.next_run_at if s else None, "copies": st.copies if st else 0, "size_bytes": int(st.size) if st else 0,
            "last_ok_at": last_ok, "last_status": lt.status if lt else None, "last_error": lt.error if lt else None,
            "late": last_ok is None or now - last_ok > timedelta(hours=26),
        })
    return result


async def _claim_due(db: AsyncSession) -> uuid.UUID | None:
    """The next company whose automatic copy is due, its next hour already set - locked, so another server process
    skips it."""
    now = datetime.now(timezone.utc)
    row = (await db.execute(
        select(CompanyBackupSettings).where(CompanyBackupSettings.mode == "AUTOMATICA",
                                            CompanyBackupSettings.next_run_at <= now)
        .order_by(CompanyBackupSettings.next_run_at).limit(1).with_for_update(skip_locked=True)
    )).scalar_one_or_none()
    if row is None:
        return None
    row.next_run_at = next_run(row.times, now)
    company_id = row.company_id
    await db.commit()
    return company_id


async def run_due_backups(db: AsyncSession) -> int:
    """Every automatic copy due now, one company after another."""
    done = 0
    while (company_id := await _claim_due(db)) is not None:
        await make_backup(db, company_id, "AUTOMATICA")
        done += 1
    return done


async def backup_loop() -> None:
    """Started with the application: every minute, the automatic copies due."""
    from app.core.database import AsyncSessionLocal
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_due_backups(db)
        except Exception:  # noqa: BLE001 - the loop never stops on one failure
            log.exception("backup loop failed")
        await asyncio.sleep(60)
