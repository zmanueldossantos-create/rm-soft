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


class SupplierNifRequiredError(Exception):
    """A supplier of Angola needs its NIF - the purchase invoices are declared with it."""


# The supplier of the purchases from someone without a NIF (a market seller, a small shop): the anonymous NIF of the
# AGT, as the Consumidor final of the sales - every company has it from its creation (see ensure_generic_supplier).
GENERIC_SUPPLIER_NAME = "Fornecedor diverso"
GENERIC_SUPPLIER_NIF = "999999999"


async def ensure_generic_supplier(db: AsyncSession, company_id: uuid.UUID) -> None:
    """Creates the company's «Fornecedor diverso» (NIF 999999999) when it has none - flush only, in the caller's
    transaction. Kept when it exists, whatever it was renamed to (found by its anonymous NIF)."""
    exists = (await db.execute(select(Supplier.id).where(
        Supplier.company_id == company_id, Supplier.nif == GENERIC_SUPPLIER_NIF).limit(1))).first()
    taken = (await db.execute(select(Supplier.id).where(
        Supplier.company_id == company_id, Supplier.name == GENERIC_SUPPLIER_NAME).limit(1))).first()
    if exists is None and taken is None:
        db.add(Supplier(company_id=company_id, name=GENERIC_SUPPLIER_NAME, nif=GENERIC_SUPPLIER_NIF,
                        notes="Compras a quem não tem NIF (mercado, pequeno comércio) - NIF anónimo da AGT"))
        await db.flush()


async def _check_nif(db: AsyncSession, nif: str | None, country_id: uuid.UUID | None) -> None:
    from app.models.country import Country
    code = None
    if country_id is not None:
        code = (await db.execute(select(Country.code).where(Country.id == country_id))).scalar_one_or_none()
    if (code is None or code == "AO") and not (nif or "").strip():
        raise SupplierNifRequiredError("O NIF é obrigatório para um fornecedor de Angola")


def _clean_iban(iban: str | None) -> str | None:
    """The IBAN as typed, without its spaces and in capitals (AO06 0040 ... -> AO060040...); empty = none."""
    clean = "".join((iban or "").split()).upper()
    return clean or None


async def create_supplier(
    db: AsyncSession, company_id: uuid.UUID, name: str,
    nif: str | None = None, phone_number: str | None = None, email: str | None = None,
    address: str | None = None, payment_terms: str | None = None, notes: str | None = None,
    trade_name: str | None = None, country_id: uuid.UUID | None = None, iban: str | None = None,
) -> Supplier:
    await _check_nif(db, nif, country_id)
    existing_result = await db.execute(
        select(Supplier).where(Supplier.company_id == company_id, Supplier.name == name)
    )
    if existing_result.scalar_one_or_none() is not None:
        raise SupplierAlreadyExistsError(f"Já existe um fornecedor chamado '{name}'")

    supplier = Supplier(
        company_id=company_id, name=name, nif=nif, phone_number=phone_number,
        email=email, address=address, payment_terms=payment_terms, notes=notes,
        trade_name=trade_name, country_id=country_id, iban=_clean_iban(iban),
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    from app.services.account_mapping_service import sync_after_create  # its sub-account (Contabilidade)
    await sync_after_create(db, company_id, supplier)
    return supplier


async def get_supplier_or_raise(db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id, Supplier.company_id == company_id))
    supplier = result.scalar_one_or_none()
    if supplier is None:
        raise SupplierNotFoundError("Fornecedor não encontrado")
    return supplier


async def list_suppliers(db: AsyncSession, company_id: uuid.UUID) -> list[Supplier]:
    result = await db.execute(select(Supplier).where(Supplier.company_id == company_id).order_by(Supplier.name))
    return list(result.scalars().all())


async def update_supplier(
    db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID, name: str,
    nif: str | None = None, phone_number: str | None = None, email: str | None = None,
    address: str | None = None, payment_terms: str | None = None, notes: str | None = None,
    trade_name: str | None = None, country_id: uuid.UUID | None = None, iban: str | None = None,
) -> Supplier:
    supplier = await get_supplier_or_raise(db, company_id, supplier_id)
    await _check_nif(db, nif, country_id)
    if name != supplier.name:
        existing_result = await db.execute(
            select(Supplier).where(Supplier.company_id == company_id, Supplier.name == name, Supplier.id != supplier_id)
        )
        if existing_result.scalar_one_or_none() is not None:
            raise SupplierAlreadyExistsError(f"Já existe um fornecedor chamado '{name}'")

    supplier.name = name
    supplier.nif = nif
    supplier.phone_number = phone_number
    supplier.email = email
    supplier.address = address
    supplier.payment_terms = payment_terms
    supplier.notes = notes
    supplier.trade_name = trade_name
    supplier.country_id = country_id
    supplier.iban = _clean_iban(iban)
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def toggle_supplier_status(db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
    supplier = await get_supplier_or_raise(db, company_id, supplier_id)
    supplier.is_active = not supplier.is_active
    await db.commit()
    await db.refresh(supplier)
    return supplier
