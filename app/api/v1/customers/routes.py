"""
Customer routes - scoped to the caller's company (multi-tenant isolation, section 2.5 v7).
Accessible to GESTOR/ADMIN of the company.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.customer import (
    CustomerCreateRequest, CustomerUpdateRequest, CustomerResponse,
    CustomerBankLinkRequest, CustomerBankLinkResponse, CustomerCodeSuggestionResponse,
)
from app.services.customer_service import (
    create_customer,
    list_customers,
    update_customer,
    toggle_customer_status,
    suggest_next_customer_code,
    list_customer_bank_links,
    add_customer_bank_link,
    remove_customer_bank_link,
    CustomerAlreadyExistsError,
    CustomerNotFoundError,
    BankLinkNotFoundError,
)

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.get("/suggest-code", response_model=CustomerCodeSuggestionResponse)
async def get_suggested_code(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("customers:manage")),
):
    """Suggests the next sequential customer code - purely a suggestion, the form field stays freely editable."""
    code = await suggest_next_customer_code(db, current_user.company_id)
    return {"suggested_code": code}


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_new_customer(
    payload: CustomerCreateRequest,
    db: AsyncSession = Depends(get_db),
    # Explicit list, not the shared ALLOWED_ROLES - CAIXA needs to create a
    # customer inline (Reservas' quick-add "Hospede" modal) without gaining the
    # broader customer-management access ALLOWED_ROLES grants elsewhere in this file.
    current_user: User = Depends(require_permission("customers:create")),
):
    """Creates a customer within the caller's company."""
    try:
        customer = await create_customer(
            db,
            company_id=current_user.company_id,
            name=payload.name,
            nif=payload.nif,
            email=payload.email,
            phone_number=payload.phone_number,
            address=payload.address,
            customer_code=payload.customer_code,
            legal_person_type=payload.legal_person_type,
            is_final_consumer=payload.is_final_consumer,
            description=payload.description,
            registration_date=payload.registration_date,
            fiscal_name=payload.fiscal_name,
            currency_id=payload.currency_id,
            country_id=payload.country_id,
            province_id=payload.province_id,
            city=payload.city,
            payment_term_id=payload.payment_term_id,
            payment_method_id=payload.payment_method_id,
            withholding_tax_id=payload.withholding_tax_id,
        )
    except CustomerAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return customer


@router.get("", response_model=list[CustomerResponse])
async def get_customers(
    db: AsyncSession = Depends(get_db),
    # Explicit list - CAIXA needs this for Reservas' "Hospede" selector.
    current_user: User = Depends(require_permission("customers:view")),
):
    """Lists all customers belonging to the caller's company."""
    return await list_customers(db, current_user.company_id)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def edit_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("customers:manage")),
):
    """Updates a customer's editable fields, scoped to the caller's company."""
    try:
        customer = await update_customer(
            db,
            company_id=current_user.company_id,
            customer_id=customer_id,
            name=payload.name,
            nif=payload.nif,
            email=payload.email,
            phone_number=payload.phone_number,
            address=payload.address,
            customer_code=payload.customer_code,
            legal_person_type=payload.legal_person_type,
            is_final_consumer=payload.is_final_consumer,
            description=payload.description,
            registration_date=payload.registration_date,
            fiscal_name=payload.fiscal_name,
            currency_id=payload.currency_id,
            country_id=payload.country_id,
            province_id=payload.province_id,
            city=payload.city,
            payment_term_id=payload.payment_term_id,
            payment_method_id=payload.payment_method_id,
            withholding_tax_id=payload.withholding_tax_id,
            status=payload.status,
        )
    except CustomerAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return customer


@router.patch("/{customer_id}/toggle-status", response_model=CustomerResponse)
async def toggle_status(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("customers:manage")),
):
    """Activates or deactivates a customer."""
    try:
        customer = await toggle_customer_status(db, current_user.company_id, customer_id)
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return customer


# ---------- Bank account links (Contas Bancarias / Documentos Vendas) ----------

@router.get("/{customer_id}/bank-links", response_model=list[CustomerBankLinkResponse])
async def get_customer_bank_links(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("customers:manage")),
):
    return await list_customer_bank_links(db, current_user.company_id, customer_id)


@router.post("/{customer_id}/bank-links", response_model=CustomerBankLinkResponse, status_code=status.HTTP_201_CREATED)
async def post_customer_bank_link(
    customer_id: uuid.UUID,
    payload: CustomerBankLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("customers:manage")),
):
    try:
        return await add_customer_bank_link(db, current_user.company_id, customer_id, payload.company_bank_account_id)
    except (CustomerNotFoundError, BankLinkNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{customer_id}/bank-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_bank_link(
    customer_id: uuid.UUID,
    link_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("customers:manage")),
):
    try:
        await remove_customer_bank_link(db, current_user.company_id, link_id)
    except BankLinkNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))