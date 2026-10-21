"""
Cópia de segurança de uma empresa (SUPER_ADMIN): «Exportar» writes ONE company - every row it owns, its images and
logo - to a .zip file; «Restaurar» puts that file back, identical (same ids, same documents, same hashes, same
numbering, same users and passwords), on this platform or on another installation of the same version.

The file:
    manifest.json          format, software version (alembic head), the company, the date, the row counts
    data/<table>.json      the company's rows, table by table
    catalog/<table>.json   the platform catalog rows they point to (currencies, units, VAT motives, document types...):
                           on another installation the same entries have other ids - they are found again by their
                           code (or name), and only an entry that does not exist there is added
    users.json             platform users the rows name (a document issued during a support access): found again by
                           phone, else kept as an inactive account, so «Criado por» still names them
    files/uploads/...      the company's images (logo, articles)

A restore is refused when the company already exists here (same id, NIF, name, email, phone or address) - it never
overwrites a company that kept working - or when the file comes from another version of the software.
Secrets saved encrypted (email password, AI key) are only readable on an installation with the same JWT_SECRET_KEY.
"""
import base64
import enum
import io
import json
import os
import uuid
import zipfile
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Table, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  (every table registered on Base.metadata)
from app.core.database import Base
from app.core.security import hash_password
from app.models.company import Company
from app.models.user import User, UserRole

FORMAT = 1
_SKIPPED = {"ai_link_codes"}  # one-time linking codes: worthless once the moment passed


class BackupError(Exception):
    """Raised when a backup file cannot be restored (unreadable, other version, company already here)."""


# ---------------------------------------------------------------------------------------------------------------- tables

def _tables() -> tuple[list[Table], list[Table], list[Table]]:
    """The company's own tables (with company_id), its child tables (lines: no company_id, under a company row) and
    the platform's catalogs - each in an order where a row comes after the rows it points to."""
    ordered = [t for t in Base.metadata.sorted_tables if t.name not in _SKIPPED]
    owned = [t for t in ordered if "company_id" in t.c and t.name != "companies"]
    owned_names = {t.name for t in owned} | {"companies"}
    children = [t for t in ordered if "company_id" not in t.c and t.name != "companies"
                and any(fk.column.table.name in owned_names for c in t.c for fk in c.foreign_keys)]
    child_names = {t.name for t in children}
    catalogs = [t for t in ordered if t.name not in owned_names and t.name not in child_names]
    return owned, children, catalogs


def _fk_target(column) -> str | None:
    fk = next(iter(column.foreign_keys), None)
    return fk.column.table.name if fk is not None else None


def software_version() -> str:
    """The database version this software expects (the last migration): a file restores only into the same one."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    root = Path(__file__).resolve().parent.parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


# ------------------------------------------------------------------------------------------------------- values <-> JSON

def _to_json(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, bytes):
        return base64.b64encode(value).decode()
    if isinstance(value, (list, tuple)):
        return [_to_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_json(v) for k, v in value.items()}
    return str(value)


def _from_json(column, value):
    if value is None:
        return None
    kind = type(column.type).__name__
    if kind == "UUID":
        return uuid.UUID(value)
    if kind == "Numeric":
        return Decimal(value)
    if kind == "DateTime":
        return datetime.fromisoformat(value)
    if kind == "Date":
        return date.fromisoformat(value)
    if kind == "Time":
        return time.fromisoformat(value)
    if kind == "Enum" and getattr(column.type, "enum_class", None) is not None:
        return column.type.enum_class[value]
    if kind == "LargeBinary":
        return base64.b64decode(value)
    return value


def _row_json(row) -> dict:
    return {k: _to_json(v) for k, v in row.items()}


# ------------------------------------------------------------------------------------------------------------- export

async def export_company(db: AsyncSession, company_id: uuid.UUID) -> tuple[bytes, str]:
    """The company's backup file (.zip) and its file name."""
    company = await db.get(Company, company_id)
    if company is None:
        raise BackupError("Empresa não encontrada")
    owned, children, catalogs = _tables()
    data: dict[str, list[dict]] = {}
    ids: dict[str, set] = {}

    companies = Base.metadata.tables["companies"]
    rows = (await db.execute(select(companies).where(companies.c.id == company_id))).mappings().all()
    data["companies"], ids["companies"] = [dict(r) for r in rows], {company_id}

    for table in owned:
        rows = (await db.execute(select(table).where(table.c.company_id == company_id))).mappings().all()
        data[table.name] = [dict(r) for r in rows]
        if "id" in table.c:
            ids[table.name] = {r["id"] for r in rows}
    for table in children:  # lines: under the company's own rows (their first required link to one)
        parent = next(c for c in table.c if c.foreign_keys and not c.nullable and _fk_target(c) in ids) \
            if any(c.foreign_keys and not c.nullable and _fk_target(c) in ids for c in table.c) \
            else next(c for c in table.c if c.foreign_keys and _fk_target(c) in ids)
        parent_ids = list(ids[_fk_target(parent)])
        rows = []
        for start in range(0, len(parent_ids), 5000):
            rows += (await db.execute(select(table).where(parent.in_(parent_ids[start:start + 5000])))).mappings().all()
        data[table.name] = [dict(r) for r in rows]
        if "id" in table.c:
            ids[table.name] = {r["id"] for r in rows}

    # the platform catalog rows they point to, and the ones those point to (a province's country...)
    catalog_names = {t.name for t in catalogs}
    wanted: dict[str, set] = {}

    def want_from(table: Table, rows: list[dict]):
        for column in table.c:
            target = _fk_target(column)
            if target in catalog_names:
                wanted.setdefault(target, set()).update(r[column.name] for r in rows if r[column.name] is not None)

    for name, rows in data.items():
        want_from(Base.metadata.tables[name], rows)
    catalog_data: dict[str, list[dict]] = {}
    for table in reversed(catalogs):  # a catalog after the ones pointing to it: its own links are wanted by then
        if table.name not in wanted or "id" not in table.c:
            continue
        rows = (await db.execute(select(table).where(table.c.id.in_(list(wanted[table.name]))))).mappings().all()
        catalog_data[table.name] = [dict(r) for r in rows]
        want_from(table, catalog_data[table.name])

    # platform users the rows name (not the company's own users)
    company_users = ids.get("users", set())
    user_ids = set()
    for name, rows in data.items():
        for column in Base.metadata.tables[name].c:
            if _fk_target(column) == "users":
                user_ids.update(r[column.name] for r in rows if r[column.name] is not None)
    outside = list(user_ids - company_users)
    platform_users = [] if not outside else [
        {"id": str(u.id), "full_name": u.full_name, "phone_number": u.phone_number, "role": u.role.name}
        for u in (await db.execute(select(User).where(User.id.in_(outside)))).scalars().all()]

    # its images: every /uploads/... path its rows hold
    files = sorted({v for rows in data.values() for r in rows for v in r.values()
                    if isinstance(v, str) and v.startswith("/uploads/")})

    exported_at = datetime.now(timezone.utc)
    manifest = {
        "format": FORMAT, "version": software_version(), "exported_at": exported_at.isoformat(),
        "company": {"id": str(company.id), "name": company.name, "short_name": company.short_name, "nif": company.nif},
        "counts": {name: len(rows) for name, rows in data.items() if rows},
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for name, rows in data.items():
            if rows:
                archive.writestr(f"data/{name}.json", json.dumps([_row_json(r) for r in rows], ensure_ascii=False))
        for name, rows in catalog_data.items():
            archive.writestr(f"catalog/{name}.json", json.dumps([_row_json(r) for r in rows], ensure_ascii=False))
        archive.writestr("users.json", json.dumps(platform_users, ensure_ascii=False))
        for path in files:
            local = path.lstrip("/")
            if os.path.isfile(local):
                archive.write(local, "files/" + local)
    slug = "".join(ch if ch.isalnum() else "-" for ch in (company.short_name or company.name)).strip("-").lower()[:40]
    return buffer.getvalue(), f"rmsoft_{slug}_{company.nif}_{exported_at:%Y%m%d_%H%M}.zip"


# ------------------------------------------------------------------------------------------------------------ restore

def _read(content: bytes) -> tuple[dict, zipfile.ZipFile]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        manifest = json.loads(archive.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise BackupError("Ficheiro inválido - escolha uma cópia exportada em Empresas («Exportar»)")
    if manifest.get("format") != FORMAT:
        raise BackupError("Formato de cópia desconhecido")
    return manifest, archive


def _load(archive: zipfile.ZipFile, path: str) -> list[dict]:
    try:
        return json.loads(archive.read(path))
    except KeyError:
        return []


async def _conflicts(db: AsyncSession, company_row: dict) -> list[str]:
    """What already exists here with this company's identity: a restore never overwrites."""
    checks = [("id", "Esta empresa já existe nesta plataforma"), ("nif", "Já existe uma empresa com o NIF {}"),
              ("name", "Já existe uma empresa com o nome {}"), ("email", "Já existe uma empresa com o email {}"),
              ("phone_number", "Já existe uma empresa com o telefone {}"),
              ("subdomain", "O endereço {} já é usado por outra empresa")]
    found = []
    for field, message in checks:
        value = company_row.get(field)
        if value is None:
            continue
        column = getattr(Company, field)
        exists = (await db.execute(select(Company.id).where(column == _from_json(Company.__table__.c[field], value)))).first()
        if exists:
            found.append(message.format(value))
            if field == "id":
                break
    return found


def preview_text(manifest: dict) -> dict:
    """What a file holds, shown before restoring it."""
    counts = manifest.get("counts", {})
    return {
        "company": manifest["company"], "exported_at": manifest["exported_at"], "version": manifest["version"],
        "same_version": manifest["version"] == software_version(),
        "counts": {"faturas": counts.get("invoices", 0), "clientes": counts.get("customers", 0),
                   "artigos": counts.get("products", 0), "servicos": counts.get("services", 0),
                   "fornecedores": counts.get("suppliers", 0), "utilizadores": counts.get("users", 0),
                   "movimentos_de_stock": counts.get("stock_movements", 0)},
    }


async def inspect_backup(db: AsyncSession, content: bytes) -> dict:
    """«Restaurar» first step: what the file holds, and what would stop it."""
    manifest, archive = _read(content)
    [company_row] = _load(archive, "data/companies.json") or [{}]
    result = preview_text(manifest)
    problems = [] if result["same_version"] else [
        "Ficheiro de outra versão do software - atualize as duas instalações para a mesma versão"]
    result["problems"] = problems + await _conflicts(db, company_row)
    return result


async def _natural_match(db: AsyncSession, table: Table, row: dict, mapped: dict) -> object | None:
    """The id of the same catalog entry here: by its unique columns, else by code, else by name (and its links)."""
    keys = next((tuple(c.name for c in u.columns) for u in table.constraints if isinstance(u, UniqueConstraint)), None)
    keys = keys or next(((c.name,) for c in table.c if c.unique), None)
    if keys is None:
        base = "code" if "code" in table.c else "name" if "name" in table.c else None
        if base is None:
            return None
        keys = (base,) + tuple(c.name for c in table.c if c.foreign_keys)
    condition = []
    for key in keys:
        value = row.get(key)
        if _fk_target(table.c[key]) is not None and value is not None:
            value = mapped.get(_fk_target(table.c[key]), {}).get(value, value)
        condition.append(table.c[key].is_(None) if value is None else table.c[key] == value)
    found = (await db.execute(select(table.c.id).where(*condition).limit(1))).first()
    return found[0] if found else None


def _typed(table: Table, raw: dict) -> dict:
    return {k: _from_json(table.c[k], v) for k, v in raw.items() if k in table.c}


async def restore_company(db: AsyncSession, content: bytes) -> dict:
    """Puts a backup file back: the company with all its rows, identical. All or nothing; the images are written once
    the restore is committed."""
    manifest, archive = _read(content)
    if manifest["version"] != software_version():
        raise BackupError("Ficheiro de outra versão do software - atualize as duas instalações para a mesma versão")
    [company_raw] = _load(archive, "data/companies.json") or [None]
    if company_raw is None:
        raise BackupError("Ficheiro sem empresa")
    problems = await _conflicts(db, company_raw)
    if problems:
        raise BackupError(problems[0])

    owned, children, catalogs = _tables()
    mapped: dict[str, dict] = {}  # table -> {id in the file: id here}, for the catalogs and the platform users

    # 1. the catalog entries: the same entry here, else added
    for table in catalogs:
        for raw in _load(archive, f"catalog/{table.name}.json"):
            row = _typed(table, raw)
            if (await db.execute(select(table.c.id).where(table.c.id == row["id"]))).first():
                mapped.setdefault(table.name, {})[row["id"]] = row["id"]
                continue
            match = await _natural_match(db, table, row, mapped)
            if match is None:
                for column in table.c:
                    target = _fk_target(column)
                    if target and row.get(column.name) is not None:
                        row[column.name] = mapped.get(target, {}).get(row[column.name], row[column.name])
                await db.execute(table.insert().values(**row))
                match = row["id"]
            mapped.setdefault(table.name, {})[row["id"]] = match

    # 2. the platform users the rows name: the same person here (by phone), else an inactive account with that name
    for raw in _load(archive, "users.json"):
        user_id = uuid.UUID(raw["id"])
        here = await db.get(User, user_id)
        if here is None:
            here = (await db.execute(select(User).where(User.company_id.is_(None),
                                                        User.phone_number == raw["phone_number"]))).scalars().first()
        if here is None:
            here = User(id=user_id, company_id=None, full_name=raw["full_name"], phone_number=raw["phone_number"],
                        role=UserRole[raw["role"]], is_active=False, password_hash=hash_password(uuid.uuid4().hex))
            db.add(here)
            await db.flush()
        mapped.setdefault("users", {})[user_id] = here.id

    # 3. the company and its rows, in order; a link to a row not inserted yet (a cycle, a row of the same table)
    #    is written once every row is in
    order = ["companies"] + [t.name for t in owned] + [t.name for t in children]
    position = {name: i for i, name in enumerate(order)}
    pending: list[tuple[Table, dict, dict]] = []
    counts = {}
    for name in order:
        table = Base.metadata.tables[name]
        raw_rows = _load(archive, f"data/{name}.json")
        if not raw_rows:
            continue
        rows = []
        for raw in raw_rows:
            row = _typed(table, raw)
            later = {}
            for column in table.c:
                target = _fk_target(column)
                value = row.get(column.name)
                if target is None or value is None:
                    continue
                if target in mapped and value in mapped[target]:
                    row[column.name] = mapped[target][value]
                elif target in position and position[target] >= position[name]:
                    later[column.name] = value
                    row[column.name] = None
            if later:
                pending.append((table, {c.name: row[c.name] for c in table.primary_key.columns}, later))
            rows.append(row)
        await db.execute(table.insert(), rows)
        counts[name] = len(rows)
    for table, key, later in pending:
        await db.execute(table.update().where(*[table.c[k] == v for k, v in key.items()]).values(**later))

    files = [n for n in archive.namelist() if n.startswith("files/uploads/") and not n.endswith("/")]
    await db.commit()
    for name in files:  # the images, at their own place (their names carry the restored ids)
        target = name[len("files/"):]
        if ".." in Path(target).parts:
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as out:
            out.write(archive.read(name))
    return {"company_id": company_raw["id"], "name": company_raw["name"], **preview_text(manifest)["counts"]}
