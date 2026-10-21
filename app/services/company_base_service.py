"""
«Nova empresa» > Base: a new company starts with the catalog of a company's backup file (made with «Exportar») - a
«Comércio geral» prepared once, reused for each new shop instead of typing it again.

What can be taken, by part:
- "artigos": the article categories, the pharmaceutical forms, the articles (price, barcode, unit, flags, image), their
  sale units and their recipes - never their stock, lots, locations or average cost;
- "servicos": the service types, the resource types and the services;
- "fornecedores": the suppliers.
Never: customers (another company's clients), documents, movements, periods, series, users, cash points.

Every row gets a new id and belongs to the new company; its links point to the new company's own rows (its VAT rates
matched by tax category) and to this platform's catalog entries (found by code, added when missing). The new company
takes the file's fiscal regime, so every rate the articles use is one it may use.

The file is uploaded once (inspect_base: kept under a token for an hour), then used by the creation (create_company),
in its own transaction: a refused copy creates nothing.
"""
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.company import Company
from app.models.fiscal_regime import FiscalRegime
from app.models.vat import VAT
from app.services.company_backup_service import BackupError, _fk_target, _load, _read, _typed, map_catalogs
import zipfile

BASE_PARTS = {
    "artigos": ["product_categories", "pharmaceutical_forms", "products", "product_sale_units", "recipe_ingredients"],
    "servicos": ["service_types", "resource_type_catalog", "services"],
    "fornecedores": ["suppliers"],
}
_RESET = {"products": {"average_cost": None}}  # the cost comes from the new company's own purchases
_KEEP_DIR = Path("uploads") / "tmp_bases"
_KEEP_SECONDS = 3600


@dataclass
class BaseCopy:
    """What a copy did (shown after the creation) and the images to write once it is committed."""
    counts: dict[str, int] = field(default_factory=dict)
    images: list[tuple[bytes, str]] = field(default_factory=list)  # (content, target file)


def _kept(token: str) -> Path:
    try:
        return _KEEP_DIR / f"{uuid.UUID(token)}.zip"
    except ValueError:
        raise BackupError("Ficheiro de base expirado - escolha-o de novo")


def _clean_old() -> None:
    if not _KEEP_DIR.is_dir():
        return
    for old in _KEEP_DIR.glob("*.zip"):
        if time.time() - old.stat().st_mtime > _KEEP_SECONDS:
            old.unlink(missing_ok=True)


async def _file_regime(db: AsyncSession, archive: zipfile.ZipFile) -> FiscalRegime | None:
    """The file company's fiscal regime, found here by its name."""
    [company] = _load(archive, "data/companies.json") or [{}]
    regime_id = company.get("fiscal_regime_id")
    names = {r["id"]: r["name"] for r in _load(archive, "catalog/fiscal_regimes.json")}
    if regime_id is None or regime_id not in names:
        return None
    return (await db.execute(select(FiscalRegime).where(FiscalRegime.name == names[regime_id]))).scalar_one_or_none()


async def inspect_base(db: AsyncSession, content: bytes) -> dict:
    """«Base» first step: what the file can give a new company, and the regime it takes. The file is kept an hour
    under the returned token, for the creation."""
    manifest, archive = _read(content)
    counts = {part: len(_load(archive, f"data/{tables[2] if part == 'artigos' else tables[-1]}.json"))
              for part, tables in BASE_PARTS.items()}
    regime = await _file_regime(db, archive)
    problems = [] if regime is not None else ["O regime fiscal da empresa do ficheiro não existe nesta plataforma"]
    _clean_old()
    token = str(uuid.uuid4())
    _KEEP_DIR.mkdir(parents=True, exist_ok=True)
    _kept(token).write_bytes(content)
    return {"token": token, "company": manifest["company"], "exported_at": manifest["exported_at"],
            "fiscal_regime_id": regime.id if regime else None, "fiscal_regime_name": regime.name if regime else None,
            "counts": counts, "problems": problems}


async def copy_base(db: AsyncSession, token: str, target: Company, parts: list[str]) -> BaseCopy:
    """Copies the chosen parts of the kept file into the new company - in the creation's transaction. The new
    company's VAT rates must already be flushed."""
    parts = [p for p in BASE_PARTS if p in set(parts or [])]
    if not parts:
        raise BackupError("Escolha o que copiar da base (artigos, serviços ou fornecedores)")
    path = _kept(token)
    if not path.is_file():
        raise BackupError("Ficheiro de base expirado - escolha-o de novo")
    _, archive = _read(path.read_bytes())
    regime = await _file_regime(db, archive)
    if regime is None or regime.id != target.fiscal_regime_id:
        raise BackupError("A nova empresa tem de ter o regime fiscal da empresa do ficheiro")

    mapped = await map_catalogs(db, archive)  # units, VAT motives, withholdings, countries... found or added here
    target_vat = {v.tax_category: v.id for v in (await db.execute(select(VAT).where(VAT.company_id == target.id))).scalars()}
    file_vat = {}
    for raw in _load(archive, "data/vat_rates.json"):
        row = _typed(VAT.__table__, raw)
        if row["tax_category"] not in target_vat:  # a category the regime no longer allows: kept, inactive
            new = VAT(company_id=target.id, name=row["name"], rate=row["rate"], tax_category=row["tax_category"], is_active=False)
            db.add(new)
            await db.flush()
            target_vat[row["tax_category"]] = new.id
        file_vat[row["id"]] = target_vat[row["tax_category"]]
    mapped["vat_rates"] = file_vat

    copy = BaseCopy()
    new_ids: dict[str, dict] = {}  # table -> {id in the file: new id}
    copied = [name for part in parts for name in BASE_PARTS[part]]
    pending = []
    for name in copied:
        table = Base.metadata.tables[name]
        rows = []
        for raw in _load(archive, f"data/{name}.json"):
            row = _typed(table, raw)
            row.update(_RESET.get(name, {}))
            later = {}
            skip = False
            for column in table.c:
                target_table = _fk_target(column)
                value = row.get(column.name)
                if column.name == "company_id":
                    row[column.name] = target.id
                elif target_table is None or value is None:
                    continue
                elif target_table in mapped:  # a platform catalog entry, or one of the new company's VAT rates
                    row[column.name] = mapped[target_table].get(value)
                elif target_table == name:  # a row of the same table: linked once all are in
                    later[column.name] = value
                    row[column.name] = None
                elif target_table in new_ids:
                    row[column.name] = new_ids[target_table].get(value)
                    if row[column.name] is None and not column.nullable:
                        skip = True  # its parent was not copied (e.g. a recipe of an article left out)
                elif target_table in copied:  # a table copied later (an article's yield unit)
                    later[column.name] = value
                    row[column.name] = None
                else:  # a row of the file company not copied (a warehouse, a customer...): no link
                    if not column.nullable:
                        skip = True
                    row[column.name] = None
            if skip:
                continue
            old_id = row["id"]
            row["id"] = uuid.uuid4()
            new_ids.setdefault(name, {})[old_id] = row["id"]
            image = row.get("image_path")
            if isinstance(image, str) and image.startswith("/uploads/"):  # its own image file, under its new id
                member = "files" + image
                if member in archive.namelist():
                    new_path = f"/uploads/products/{row['id']}{os.path.splitext(image)[1]}"
                    copy.images.append((archive.read(member), new_path.lstrip("/")))
                    row["image_path"] = new_path
                else:
                    row["image_path"] = None
            if later:
                pending.append((table, row["id"], later))
            rows.append(row)
        if rows:
            await db.execute(table.insert(), rows)
        copy.counts[name] = len(rows)
    for table, row_id, later in pending:
        values = {k: new_ids.get(_fk_target(table.c[k]), {}).get(v) for k, v in later.items()}
        await db.execute(table.update().where(table.c.id == row_id).values(**values))
    path.unlink(missing_ok=True)
    return copy


def write_images(copy: BaseCopy) -> None:
    """After the creation is committed: the copied articles' own image files."""
    for content, target in copy.images:
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as out:
                out.write(content)
        except OSError:
            pass


def base_counts(copy: BaseCopy) -> dict[str, int]:
    """What was copied, in the words of the screen."""
    labels = {"product_categories": "categorias", "products": "artigos", "product_sale_units": "unidades_de_venda",
              "recipe_ingredients": "receitas", "service_types": "tipos_de_servico", "services": "servicos",
              "suppliers": "fornecedores"}
    return {labels[k]: v for k, v in copy.counts.items() if k in labels}

