"""
Service layer for Supplier - simple catalog CRUD, mirroring
customer_service.py's shape but without the AGT-driven NIF requirement
(see Supplier model docstring for why).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier


class SupplierNotFoundError(Exception):
    pass


class SupplierAlreadyExistsError(Exception):
    pass


async def create_supplier(
    db: AsyncSession, company_id: uuid.UUID, name: str,
    nif: str | None = None, phone_number: str | None = None, email: str | None = None,
    address: str | None = None, payment_terms: str | None = None, notes: str | None = None,
) -> Supplier:
    existing_result = await db.execute(
        select(Supplier).where(Supplier.company_id == company_id, Supplier.name == name)
    )
    if existing_result.scalar_one_or_none() is not None:
        raise SupplierAlreadyExistsError(f"Ja existe um fornecedor chamado '{name}'")

    supplier = Supplier(
        company_id=company_id, name=name, nif=nif, phone_number=phone_number,
        email=email, address=address, payment_terms=payment_terms, notes=notes,
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def get_supplier_or_raise(db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id, Supplier.company_id == company_id))
    supplier = result.scalar_one_or_none()
    if supplier is None:
        raise SupplierNotFoundError("Fornecedor nao encontrado")
    return supplier


async def list_suppliers(db: AsyncSession, company_id: uuid.UUID) -> list[Supplier]:
    result = await db.execute(select(Supplier).where(Supplier.company_id == company_id).order_by(Supplier.name))
    return list(result.scalars().all())


async def update_supplier(
    db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID, name: str,
    nif: str | None = None, phone_number: str | None = None, email: str | None = None,
    address: str | None = None, payment_terms: str | None = None, notes: str | None = None,
) -> Supplier:
    supplier = await get_supplier_or_raise(db, company_id, supplier_id)
    if name != supplier.name:
        existing_result = await db.execute(
            select(Supplier).where(Supplier.company_id == company_id, Supplier.name == name, Supplier.id != supplier_id)
        )
        if existing_result.scalar_one_or_none() is not None:
            raise SupplierAlreadyExistsError(f"Ja existe um fornecedor chamado '{name}'")

    supplier.name = name
    supplier.nif = nif
    supplier.phone_number = phone_number
    supplier.email = email
    supplier.address = address
    supplier.payment_terms = payment_terms
    supplier.notes = notes
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def toggle_supplier_status(db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
    supplier = await get_supplier_or_raise(db, company_id, supplier_id)
    supplier.is_active = not supplier.is_active
    await db.commit()
    await db.refresh(supplier)
    return supplier
