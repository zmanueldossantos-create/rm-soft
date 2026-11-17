"""Recursos Humanos (capability HR): the employees' files (list, create, change, departure, readmission) and the
company's HR tables."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.schemas.employee import (
    DepartureRequest, EmployeeRequest, HrReferenceCreateRequest, HrReferenceUpdateRequest, ReadmissionRequest,
)
from app.services.employee_service import (
    EmployeeError, EmployeeNotFoundError, create_employee, create_reference, delete_reference, employee_detail,
    employee_options, list_employees, list_references, readmit_employee, register_departure, update_employee,
    update_reference,
)

router = APIRouter(prefix="/api/v1/hr", tags=["hr"])


def _refused(e: EmployeeError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(e, EmployeeNotFoundError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(e))


@router.get("/employees")
async def get_employees(status_filter: str = "ATIVOS", search: str | None = None, department_id: uuid.UUID | None = None,
                        db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    return await list_employees(db, current_user.company_id, status_filter, search, department_id)


@router.get("/employees/options")
async def get_employee_options(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    return await employee_options(db, current_user.company_id)


@router.get("/employees/{employee_id}")
async def get_employee(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("hr:view"))):
    try:
        return await employee_detail(db, current_user.company_id, employee_id)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def post_employee(payload: EmployeeRequest, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("hr:manage"))):
    try:
        return await create_employee(db, current_user.company_id, current_user.id, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.put("/employees/{employee_id}")
async def put_employee(employee_id: uuid.UUID, payload: EmployeeRequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("hr:manage"))):
    try:
        return await update_employee(db, current_user.company_id, employee_id, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.post("/employees/{employee_id}/departure")
async def post_departure(employee_id: uuid.UUID, payload: DepartureRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("hr:manage"))):
    try:
        return await register_departure(db, current_user.company_id, employee_id, payload.left_on, payload.reason, payload.note)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/employees/{employee_id}/readmission")
async def post_readmission(employee_id: uuid.UUID, payload: ReadmissionRequest, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("hr:manage"))):
    try:
        return await readmit_employee(db, current_user.company_id, employee_id, payload.hired_on)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/references")
async def get_references(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:settings"))):
    return await list_references(db, current_user.company_id)


@router.post("/references", status_code=status.HTTP_201_CREATED)
async def post_reference(payload: HrReferenceCreateRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("hr:settings"))):
    try:
        return await create_reference(db, current_user.company_id, payload.kind, payload.name)
    except EmployeeError as e:
        raise _refused(e)


@router.put("/references/{reference_id}")
async def put_reference(reference_id: uuid.UUID, payload: HrReferenceUpdateRequest, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("hr:settings"))):
    try:
        return await update_reference(db, current_user.company_id, reference_id, payload.name, payload.is_active)
    except EmployeeError as e:
        raise _refused(e)


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_reference(reference_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("hr:settings"))):
    try:
        await delete_reference(db, current_user.company_id, reference_id)
    except EmployeeError as e:
        raise _refused(e)
