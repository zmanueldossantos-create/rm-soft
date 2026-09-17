"""
Business logic for customer management.
Every query is scoped to the caller's company_id (multi-tenant isolation, section 2.5 v7).
Extended (Video 2) with the 2-tab fields observed in the reference
legalized software: identificacao, dados fiscais.
"""
import uuid
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer, CustomerStatus, FINAL_CONSUMER_NIF
from app.models.customer_bank_account_link import CustomerBankAccountLink
from app.models.company_bank_account import CompanyBankAccount


class CustomerAlreadyExistsError(Exception):
    """Raised when a customer field (name or NIF) conflicts within the same company."""
    pass


class CustomerNotFoundError(Exception):
    """Raised when a customer id does not match any customer in the caller's company."""
    pass


class BankLinkNotFoundError(Exception):
    pass


async def _check_nif_available(
    db: AsyncSession,
    company_id: uuid.UUID,
    nif: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """
    Checks NIF uniqueness within the company. Name is intentionally NOT unique -
    two different real customers can share the same name (common with people),
    unlike a company name which is more distinctive. NIF is the true legal
    identifier - this same check naturally allows only ONE "Consumidor Final"
    customer per company, since they'd all share NIF 999999999.
    """
    nif_query = select(Customer).where(Customer.company_id == company_id, Customer.nif == nif)
    if exclude_id is not None:
        nif_query = nif_query.where(Customer.id != exclude_id)
    if (await db.execute(nif_query)).scalar_one_or_none() is not None:
        raise CustomerAlreadyExistsError("Ja existe um cliente registado com este NIF")


async def suggest_next_customer_code(db: AsyncSession, company_id: uuid.UUID, prefix: str = "C") -> str:
    """Suggests the next sequential customer code (e.g. "C002") - purely a suggestion, never enforced."""
    count_result = await db.execute(select(func.count()).select_from(Customer).where(Customer.company_id == company_id))
    count = count_result.scalar_one()
    return f"{prefix}{count + 1:04d}"


async def create_customer(
    db: AsyncSession,
    company_id: uuid.UUID,
    name: str,
    nif: str,
    email: str | None = None,
    phone_number: str | None = None,
    address: str | None = None,
    customer_code: str | None = None,
    legal_person_type: str = "JURIDICA",
    is_final_consumer: bool = False,
    description: str | None = None,
    registration_date: date | None = None,
    fiscal_name: str | None = None,
    currency_id: uuid.UUID | None = None,
    country_id: uuid.UUID | None = None,
    province_id: uuid.UUID | None = None,
    city: str | None = None,
    payment_term_id: uuid.UUID | None = None,
    payment_method_id: uuid.UUID | None = None,
    withholding_tax_id: uuid.UUID | None = None,
) -> Customer:
    """Creates a customer within the caller's company."""
    effective_nif = FINAL_CONSUMER_NIF if is_final_consumer else nif
    await _check_nif_available(db, company_id, effective_nif)

    customer = Customer(
        company_id=company_id,
        name=name,
        nif=effective_nif,
        email=email,
        phone_number=phone_number,
        address=address,
        customer_code=customer_code,
        legal_person_type=legal_person_type,
        is_final_consumer=is_final_consumer,
        description=description,
        registration_date=registration_date or date.today(),
        fiscal_name=fiscal_name,
        currency_id=currency_id,
        country_id=country_id,
        province_id=province_id,
        city=city,
        payment_term_id=payment_term_id,
        payment_method_id=payment_method_id,
        # Retencao only applies to pessoa coletiva (Video 2 note).
        withholding_tax_id=withholding_tax_id if legal_person_type == "JURIDICA" else None,
        status=CustomerStatus.ACTIVO,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def list_customers(db: AsyncSession, company_id: uuid.UUID) -> list[Customer]:
    """Lists all customers belonging to the caller's company."""
    result = await db.execute(
        select(Customer).where(Customer.company_id == company_id).order_by(Customer.created_at.desc())
    )
    return list(result.scalars().all())


async def get_customer_or_raise(db: AsyncSession, company_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.company_id == company_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise CustomerNotFoundError("Cliente nao encontrado")
    return customer


async def update_customer(
    db: AsyncSession,
    company_id: uuid.UUID,
    customer_id: uuid.UUID,
    name: str,
    nif: str,
    email: str | None = None,
    phone_number: str | None = None,
    address: str | None = None,
    customer_code: str | None = None,
    legal_person_type: str = "JURIDICA",
    is_final_consumer: bool = False,
    description: str | None = None,
    registration_date: date | None = None,
    fiscal_name: str | None = None,
    currency_id: uuid.UUID | None = None,
    country_id: uuid.UUID | None = None,
    province_id: uuid.UUID | None = None,
    city: str | None = None,
    payment_term_id: uuid.UUID | None = None,
    payment_method_id: uuid.UUID | None = None,
    withholding_tax_id: uuid.UUID | None = None,
    status: str = "ACTIVO",
) -> Customer:
    """Updates a customer's editable fields, scoped to the caller's company."""
    customer = await get_customer_or_raise(db, company_id, customer_id)
    effective_nif = FINAL_CONSUMER_NIF if is_final_consumer else nif
    await _check_nif_available(db, company_id, effective_nif, exclude_id=customer_id)

    customer.name = name
    customer.nif = effective_nif
    customer.email = email
    customer.phone_number = phone_number
    customer.address = address
    customer.customer_code = customer_code
    customer.legal_person_type = legal_person_type
    customer.is_final_consumer = is_final_consumer
    customer.description = description
    if registration_date is not None:
        customer.registration_date = registration_date
    customer.fiscal_name = fiscal_name
    customer.currency_id = currency_id
    customer.country_id = country_id
    customer.province_id = province_id
    customer.city = city
    customer.payment_term_id = payment_term_id
    customer.payment_method_id = payment_method_id
    customer.withholding_tax_id = withholding_tax_id if legal_person_type == "JURIDICA" else None
    customer.status = CustomerStatus(status)

    await db.commit()
    await db.refresh(customer)
    return customer


async def toggle_customer_status(db: AsyncSession, company_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    """Activates or deactivates a customer (quick toggle - separate from the richer `status` field)."""
    customer = await get_customer_or_raise(db, company_id, customer_id)
    customer.is_active = not customer.is_active
    await db.commit()
    await db.refresh(customer)
    return customer


# ---------- Bank account links (Contas Bancarias / Documentos Vendas) ----------
# SECURITY FIX (multi-tenant audit): all three functions below used to trust
# customer_id / link_id blindly, with zero company_id check - a company A
# could list, attach to, or delete another company's customer bank links just
# by knowing/guessing the UUID. Every function now re-verifies ownership.

async def list_customer_bank_links(db: AsyncSession, company_id: uuid.UUID, customer_id: uuid.UUID) -> list[CustomerBankAccountLink]:
    """Lists a customer's linked bank accounts - scoped to the caller's company via the customer itself."""
    await get_customer_or_raise(db, company_id, customer_id)
    result = await db.execute(select(CustomerBankAccountLink).where(CustomerBankAccountLink.customer_id == customer_id))
    return list(result.scalars().all())


async def add_customer_bank_link(
    db: AsyncSession, company_id: uuid.UUID, customer_id: uuid.UUID, company_bank_account_id: uuid.UUID,
) -> CustomerBankAccountLink:
    """Links one of the company's own bank accounts to a customer - both sides verified to belong to company_id."""
    await get_customer_or_raise(db, company_id, customer_id)

    account_result = await db.execute(
        select(CompanyBankAccount).where(
            CompanyBankAccount.id == company_bank_account_id, CompanyBankAccount.company_id == company_id,
        )
    )
    if account_result.scalar_one_or_none() is None:
        raise BankLinkNotFoundError("Conta bancaria nao encontrada")

    link = CustomerBankAccountLink(customer_id=customer_id, company_bank_account_id=company_bank_account_id)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def remove_customer_bank_link(db: AsyncSession, company_id: uuid.UUID, link_id: uuid.UUID) -> None:
    """Removes a bank link - scoped to the caller's company via a join through Customer."""
    result = await db.execute(
        select(CustomerBankAccountLink)
        .join(Customer, Customer.id == CustomerBankAccountLink.customer_id)
        .where(CustomerBankAccountLink.id == link_id, Customer.company_id == company_id)
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise BankLinkNotFoundError("Associacao de conta bancaria nao encontrada")
    await db.delete(link)
    await db.commit()