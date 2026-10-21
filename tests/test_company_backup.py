"""
Cópia de segurança de uma empresa (Empresas > «Exportar» / «Restaurar»): one company to a file, and back identical -
same ids, documents, hashes, numbering, users and passwords, images. Catalog entries with other ids (another
installation) are found again by their code. A restore never overwrites a company that exists here, and refuses a file
of another software version.
"""
import io
import json
import os
import shutil
import zipfile

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.main import app
from app.models.company import Company
from app.models.document_series import DocumentSeries
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.product import Product, ProductType
from app.models.user import User, UserRole
from app.services.company_backup_service import (BackupError, _tables, export_company, inspect_backup,
                                                 restore_company)


async def _wipe(db, company_id):
    """The company disappears from this platform (the crash), its catalogs stay."""
    owned, children, _ = _tables()
    ids = {}
    for table in owned:
        if "id" in table.c:
            ids[table.name] = [r[0] for r in (await db.execute(select(table.c.id).where(table.c.company_id == company_id)))]
    for table in reversed(children):
        for column in table.c:
            fk = next(iter(column.foreign_keys), None)
            if fk is not None and fk.column.table.name in ids and not column.nullable:
                await db.execute(delete(table).where(column.in_(ids[fk.column.table.name])))
                break
    for table in owned:  # links between the company's own rows first, then the rows, latest tables first
        nullable = {c.name: None for c in table.c if c.foreign_keys and c.nullable and c.name != "company_id"}
        if nullable:
            await db.execute(table.update().where(table.c.company_id == company_id).values(**nullable))
    for table in reversed(owned):
        await db.execute(delete(table).where(table.c.company_id == company_id))
    await db.execute(delete(Company).where(Company.id == company_id))
    await db.commit()


def _rewrite(content: bytes, change) -> bytes:
    """The same file with every entry passed through change(name, text)."""
    source = zipfile.ZipFile(io.BytesIO(content))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name.endswith(".json"):
                data = change(name, data.decode()).encode()
            target.writestr(name, data)
    return out.getvalue()


@pytest.fixture
def logo(company_with_essentials):
    company = company_with_essentials["company"]
    os.makedirs("uploads/logos", exist_ok=True)
    path = f"uploads/logos/{company.id}.png"
    with open(path, "wb") as f:
        f.write(b"\x89PNG-logo")
    yield path
    if os.path.exists(path):
        os.remove(path)


async def test_export_then_restore_after_a_crash(db, company_with_essentials, logo):
    from app.services.invoice_service import create_invoice
    from app.services.stock_service import receive_stock
    ctx = company_with_essentials
    company = ctx["company"]
    company_id, gestor_id = company.id, ctx["gestor"].id
    company.logo_path = "/" + logo
    product = Product(company_id=company_id, code="BK1", name="Artigo", vat_id=ctx["vat_nor"].id, price=100,
                      min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add(product)
    await db.commit()
    await receive_stock(db, company_id, product.id, 5, warehouse_id=ctx["activity_warehouse"].id)
    invoice = await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA_RECIBO",
                                   lines_input=[{"product_id": product.id, "quantity": 2}])
    invoice_id, number, invoice_hash = invoice.id, (invoice.series, invoice.number), invoice.invoice_hash
    series_next = {s.id: s.current_number for s in (await db.execute(
        select(DocumentSeries).where(DocumentSeries.company_id == company_id))).scalars()}
    unit_id, product_id = ctx["unit_un"].id, product.id

    content, filename = await export_company(db, company_id)
    assert filename.startswith("rmsoft_") and filename.endswith(".zip")
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(content)).read("manifest.json"))
    assert manifest["company"]["nif"] == company.nif and manifest["counts"]["invoices"] == 1

    # still here: refused, never overwritten
    seen = await inspect_backup(db, content)
    assert seen["counts"]["faturas"] == 1 and "já existe" in seen["problems"][0]
    with pytest.raises(BackupError, match="já existe"):
        await restore_company(db, content)
    await db.rollback()

    # the crash: the company is gone, and the file comes from an installation where the unit «UN» had another id
    await _wipe(db, company_id)
    shutil.move(logo, logo + ".bak")
    import uuid
    other_unit = str(uuid.uuid4())
    content = _rewrite(content, lambda name, text: text.replace(str(unit_id), other_unit))
    assert (await inspect_backup(db, content))["problems"] == []

    restored = await restore_company(db, content)
    assert restored["faturas"] == 1 and restored["artigos"] == 1
    db.expire_all()
    again = await db.get(Invoice, invoice_id)
    assert (again.company_id, (again.series, again.number), again.invoice_hash) == (company_id, number, invoice_hash)
    assert (await db.execute(select(func.count()).select_from(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalar_one() == 1
    assert (await db.get(Product, product_id)).unit_of_measure_id == unit_id  # found again by its code
    assert {s.id: s.current_number for s in (await db.execute(
        select(DocumentSeries).where(DocumentSeries.company_id == company_id))).scalars()} == series_next
    gestor = await db.get(User, gestor_id)
    assert verify_password("Teste@2026", gestor.password_hash)  # same users, same passwords
    with open(logo, "rb") as f:
        assert f.read() == b"\x89PNG-logo"
    os.remove(logo + ".bak")


async def test_a_platform_user_named_by_the_rows_and_another_version(db, company_with_essentials):
    """A document issued during a support access names the platform user: kept, inactive, on another installation."""
    ctx = company_with_essentials
    company_id = ctx["company"].id
    admin = User(company_id=None, full_name="Suporte Antigo", phone_number="+244923888001",
                 password_hash=hash_password("Teste@2026"), role=UserRole.SUPER_ADMIN)
    db.add(admin)
    await db.flush()
    db.add(Product(company_id=company_id, code="BK2", name="Artigo", vat_id=ctx["vat_nor"].id, price=1,
                   min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id))
    from app.models.support_session import SupportSession
    from datetime import datetime, timedelta, timezone
    db.add(SupportSession(company_id=company_id, admin_user_id=admin.id, reason="Verificar a caixa",
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    admin_id = admin.id
    content, _ = await export_company(db, company_id)

    await _wipe(db, company_id)
    await db.execute(delete(User).where(User.id == admin_id))  # another installation: that person is unknown there
    await db.commit()
    await restore_company(db, content)
    kept = await db.get(User, admin_id)
    assert (kept.full_name, kept.is_active, kept.company_id) == ("Suporte Antigo", False, None)

    # another version of the software: refused
    await _wipe(db, company_id)
    old = _rewrite(content, lambda name, text: text.replace(json.loads(text)["version"], "000old") if name == "manifest.json" else text)
    assert "outra versão" in (await inspect_backup(db, old))["problems"][0]
    with pytest.raises(BackupError, match="outra versão"):
        await restore_company(db, old)


async def test_the_routes_are_the_platforms(db, company_with_essentials):
    ctx = company_with_essentials

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            admin = User(company_id=None, full_name="Admin", phone_number="+244923888002",
                         password_hash=hash_password("Teste@2026"), role=UserRole.SUPER_ADMIN)
            db.add(admin)
            await db.commit()
            admin_token = create_access_token(subject=str(admin.id), company_id="None", role="SUPER_ADMIN")
            gestor_token = create_access_token(subject=str(ctx["gestor"].id), company_id=str(ctx["company"].id), role="GESTOR")
            url = f"/api/v1/admin/companies/{ctx['company'].id}/export"
            assert (await client.get(url, headers={"Authorization": "Bearer " + gestor_token})).status_code == 403
            got = await client.get(url, headers={"Authorization": "Bearer " + admin_token})
            assert got.status_code == 200 and got.headers["content-type"] == "application/zip"
            seen = await client.post("/api/v1/admin/companies/restore/inspect", headers={"Authorization": "Bearer " + admin_token},
                                     files={"file": ("copia.zip", got.content, "application/zip")})
            assert seen.status_code == 200 and seen.json()["problems"]
            bad = await client.post("/api/v1/admin/companies/restore", headers={"Authorization": "Bearer " + admin_token},
                                    files={"file": ("x.zip", b"nada", "application/zip")})
            assert bad.status_code == 422 and "inválido" in bad.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)
