"""
Recursos Humanos: the employee's photo and the documents of his file.

Rules:
- the photo: one per employee (a new one replaces it), JPEG, PNG or WebP, up to 2 MB;
- a document: its type (Tabelas de RH → Documentos do processo) or a description, the day it was handed in, its
  validity if it has one (a medical certificate, the BI), and the scanned file when there is one - PDF, JPEG or PNG,
  up to 5 MB; a document handed in on paper only is recorded without a file;
- the file's kind is read from its first bytes, never trusted from its name;
- everything stays in the database (personal data: never in the public /uploads) and is read with the HR rights.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.models.employee import FILE_DOCUMENT, FILE_PHOTO, EmployeeFile, HrReference
from app.services.employee_service import EmployeeError, EmployeeNotFoundError, ensure_default_references, get_employee

PHOTO_MAX = 2 * 1024 * 1024
DOCUMENT_MAX = 5 * 1024 * 1024
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
DOCUMENT_TYPES = ("application/pdf", "image/jpeg", "image/png")


def sniff(content: bytes) -> str | None:
    """The real kind of a file, from its first bytes."""
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _clean_file_name(name: str | None, kind: str) -> str:
    name = (name or "").replace("\\", "/").split("/")[-1].strip()[:150]
    extension = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[kind]
    return name or ("documento" + extension)


async def set_photo(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, employee_id: uuid.UUID,
                    file_name: str | None, content: bytes) -> dict:
    employee = await get_employee(db, company_id, employee_id)
    if not content:
        raise EmployeeError("Escolha uma fotografia")
    if len(content) > PHOTO_MAX:
        raise EmployeeError("A fotografia tem no máximo 2 MB")
    kind = sniff(content)
    if kind not in IMAGE_TYPES:
        raise EmployeeError("A fotografia tem de ser uma imagem JPEG, PNG ou WebP")
    for old in (await db.execute(select(EmployeeFile).where(
            EmployeeFile.employee_id == employee.id, EmployeeFile.kind == FILE_PHOTO))).scalars():
        await db.delete(old)
    db.add(EmployeeFile(company_id=company_id, employee_id=employee.id, kind=FILE_PHOTO, file_name=_clean_file_name(file_name, kind),
                        content_type=kind, size=len(content), content=content, uploaded_by_user_id=user_id))
    await db.commit()
    return {"has_photo": True}


async def delete_photo(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID) -> None:
    employee = await get_employee(db, company_id, employee_id)
    for old in (await db.execute(select(EmployeeFile).where(
            EmployeeFile.employee_id == employee.id, EmployeeFile.kind == FILE_PHOTO))).scalars():
        await db.delete(old)
    await db.commit()


async def get_photo(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID) -> tuple[bytes, str] | None:
    row = (await db.execute(select(EmployeeFile).options(undefer(EmployeeFile.content)).where(
        EmployeeFile.company_id == company_id, EmployeeFile.employee_id == employee_id,
        EmployeeFile.kind == FILE_PHOTO))).scalars().first()
    return (row.content, row.content_type) if row is not None and row.content else None


def _document(f: EmployeeFile, types: dict) -> dict:
    return {"id": f.id, "document_type_id": f.document_type_id, "name": types.get(f.document_type_id) or f.description,
            "description": f.description, "delivered_on": f.delivered_on, "expires_on": f.expires_on,
            "has_file": f.size is not None, "file_name": f.file_name, "content_type": f.content_type, "size": f.size,
            "created_at": f.created_at}


async def list_documents(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID) -> dict:
    """The documents handed in, and the company's document list ticked against them (what is still missing)."""
    employee = await get_employee(db, company_id, employee_id)
    await ensure_default_references(db, company_id)
    types = (await db.execute(select(HrReference).where(
        HrReference.company_id == company_id, HrReference.kind == "TIPO_DOCUMENTO")
        .order_by(HrReference.position, HrReference.name))).scalars().all()
    names = {t.id: t.name for t in types}
    files = (await db.execute(select(EmployeeFile).where(
        EmployeeFile.employee_id == employee.id, EmployeeFile.kind == FILE_DOCUMENT)
        .order_by(EmployeeFile.delivered_on.desc().nullslast(), EmployeeFile.created_at.desc()))).scalars().all()
    handed = {f.document_type_id for f in files}
    today = date.today()
    return {
        "documents": [{**_document(f, names), "expired": bool(f.expires_on and f.expires_on < today)} for f in files],
        "checklist": [{"document_type_id": t.id, "name": t.name, "delivered": t.id in handed}
                      for t in types if t.is_active or t.id in handed],
    }


async def add_document(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, employee_id: uuid.UUID,
                       document_type_id: uuid.UUID | None, description: str | None, delivered_on: date | None,
                       expires_on: date | None, file_name: str | None = None, content: bytes | None = None) -> dict:
    employee = await get_employee(db, company_id, employee_id)
    description = " ".join((description or "").split())[:200] or None
    names: dict = {}
    if document_type_id is not None:
        doc_type = (await db.execute(select(HrReference).where(
            HrReference.id == document_type_id, HrReference.company_id == company_id,
            HrReference.kind == "TIPO_DOCUMENTO"))).scalar_one_or_none()
        if doc_type is None:
            raise EmployeeError("Tipo de documento inválido")
        if not doc_type.is_active:
            raise EmployeeError(f"«{doc_type.name}» está desativado nos documentos do processo")
        names[doc_type.id] = doc_type.name
    elif not description:
        raise EmployeeError("Escolha o tipo de documento ou descreva-o")
    if delivered_on is None:
        delivered_on = date.today()
    if delivered_on > date.today():
        raise EmployeeError("A data de entrega não pode ser futura")
    if expires_on is not None and expires_on < delivered_on:
        raise EmployeeError("A validade é anterior à data de entrega")
    record = EmployeeFile(company_id=company_id, employee_id=employee.id, kind=FILE_DOCUMENT, document_type_id=document_type_id,
                          description=description, delivered_on=delivered_on, expires_on=expires_on, uploaded_by_user_id=user_id)
    if content:
        if len(content) > DOCUMENT_MAX:
            raise EmployeeError("O ficheiro tem no máximo 5 MB")
        kind = sniff(content)
        if kind not in DOCUMENT_TYPES:
            raise EmployeeError("O ficheiro tem de ser um PDF ou uma imagem JPEG ou PNG")
        record.file_name, record.content_type, record.size, record.content = _clean_file_name(file_name, kind), kind, len(content), content
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _document(record, names)


async def _get_document(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID, document_id: uuid.UUID,
                        with_content: bool = False) -> EmployeeFile:
    query = select(EmployeeFile).where(EmployeeFile.id == document_id, EmployeeFile.company_id == company_id,
                                       EmployeeFile.employee_id == employee_id, EmployeeFile.kind == FILE_DOCUMENT)
    if with_content:
        query = query.options(undefer(EmployeeFile.content))
    document = (await db.execute(query)).scalar_one_or_none()
    if document is None:
        raise EmployeeNotFoundError("Documento não encontrado")
    return document


async def get_document_file(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID,
                            document_id: uuid.UUID) -> tuple[bytes, str, str]:
    document = await _get_document(db, company_id, employee_id, document_id, with_content=True)
    if not document.content:
        raise EmployeeNotFoundError("Este documento foi entregue em papel: não tem ficheiro")
    return document.content, document.content_type, document.file_name


async def delete_document(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID, document_id: uuid.UUID) -> None:
    await db.delete(await _get_document(db, company_id, employee_id, document_id))
    await db.commit()


async def has_photo(db: AsyncSession, employee_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not employee_ids:
        return set()
    return set((await db.execute(select(EmployeeFile.employee_id).where(
        EmployeeFile.employee_id.in_(employee_ids), EmployeeFile.kind == FILE_PHOTO))).scalars())

