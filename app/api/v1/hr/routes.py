"""Recursos Humanos (capability HR): the employees' files (list, create, change, departure, readmission) and the
company's HR tables."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
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

from app.services.employee_file_service import (
    DOCUMENT_MAX, add_document, delete_document, delete_photo, get_document_file, get_photo, list_documents, set_photo,
)

router = APIRouter(prefix="/api/v1/hr", tags=["hr"])


async def _read_upload(upload: UploadFile, limit: int) -> bytes:
    """The uploaded file, refused past the limit without reading it all."""
    content = await upload.read(limit + 1)
    if len(content) > limit:
        raise EmployeeError(f"O ficheiro tem no máximo {limit // (1024 * 1024)} MB")
    return content


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


@router.get("/employees/{employee_id}/pdf")
async def get_employee_pdf(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("hr:view"))):
    """The employee's file in A4: identification, professional data, pay, qualifications, documents."""
    from app.models.company import Company
    from app.services.cash_report_service import _company_dict
    from app.utils.employee_pdf import generate_employee_pdf
    try:
        employee = await employee_detail(db, current_user.company_id, employee_id)
        documents = await list_documents(db, current_user.company_id, employee_id)
        photo = await get_photo(db, current_user.company_id, employee_id)
    except EmployeeError as e:
        raise _refused(e)
    company = await db.get(Company, current_user.company_id)
    pdf = generate_employee_pdf(employee, documents, photo[0] if photo else None, _company_dict(company))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="ficha-colaborador_{employee["number"]}.pdf"'})


@router.get("/employees/{employee_id}/photo")
async def get_employee_photo(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("hr:view"))):
    photo = await get_photo(db, current_user.company_id, employee_id)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sem fotografia")
    return Response(content=photo[0], media_type=photo[1], headers={"Cache-Control": "private, no-store"})


@router.put("/employees/{employee_id}/photo")
async def put_employee_photo(employee_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("hr:manage"))):
    try:
        content = await _read_upload(file, 2 * 1024 * 1024)
        return await set_photo(db, current_user.company_id, current_user.id, employee_id, file.filename, content)
    except EmployeeError as e:
        raise _refused(e)


@router.delete("/employees/{employee_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
async def remove_employee_photo(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("hr:manage"))):
    try:
        await delete_photo(db, current_user.company_id, employee_id)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/employees/{employee_id}/documents")
async def get_employee_documents(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(require_permission("hr:view"))):
    try:
        return await list_documents(db, current_user.company_id, employee_id)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/employees/{employee_id}/documents", status_code=status.HTTP_201_CREATED)
async def post_employee_document(employee_id: uuid.UUID, document_type_id: uuid.UUID | None = Form(None),
                                 description: str | None = Form(None), delivered_on: date | None = Form(None),
                                 expires_on: date | None = Form(None), file: UploadFile | None = File(None),
                                 db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(require_permission("hr:manage"))):
    try:
        content = await _read_upload(file, DOCUMENT_MAX) if file is not None else None
        return await add_document(db, current_user.company_id, current_user.id, employee_id, document_type_id, description,
                                  delivered_on, expires_on, file.filename if file is not None else None, content)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/employees/{employee_id}/documents/{document_id}/file")
async def get_employee_document_file(employee_id: uuid.UUID, document_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                     current_user: User = Depends(require_permission("hr:view"))):
    try:
        content, kind, name = await get_document_file(db, current_user.company_id, employee_id, document_id)
    except EmployeeError as e:
        raise _refused(e)
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    return Response(content=content, media_type=kind,
                    headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "private, no-store"})


@router.delete("/employees/{employee_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_employee_document(employee_id: uuid.UUID, document_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_permission("hr:manage"))):
    try:
        await delete_document(db, current_user.company_id, employee_id, document_id)
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
