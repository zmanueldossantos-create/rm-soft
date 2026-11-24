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
    AbsenceDecisionRequest, AbsenceRequest, VacationAdjustmentRequest, AbsenceTypeRequest, DepartureRequest, EmployeePayrollItemsRequest, HolidayRequest, EmployeeRequest, FormulaCheckRequest, HrReferenceCreateRequest,
    HrReferenceUpdateRequest, IrtTableRequest, PayrollItemRequest, PayrollSettingsRequest, ReadmissionRequest,
    SimulationRequest,
)
from app.services.employee_service import (
    EmployeeError, EmployeeNotFoundError, create_employee, create_reference, delete_reference, employee_detail,
    employee_options, list_employees, list_references, readmit_employee, register_departure, update_employee,
    update_reference,
)

from app.services.employee_file_service import (
    DOCUMENT_MAX, add_document, delete_document, delete_photo, get_document_file, get_photo, list_documents, set_photo,
)

from app.services.payroll_settings_service import (
    check_formula, create_item, delete_irt_table, delete_item, employee_items, get_payroll_settings, list_irt_tables,
    list_items, save_irt_table, set_employee_items, simulate_payslip, update_item, update_payroll_settings,
)

from app.services.hr_calendar_service import (
    count_days, delete_absence_type, delete_holiday, generate_holidays, list_absence_types, list_holidays,
    save_absence_type, save_holiday,
)

from app.services.absence_service import (
    absence_detail, absence_options, approve_absence, attach_document, cancel_absence, create_absence, list_absences,
    month_map, refuse_absence, update_absence,
)
from app.services.permission_service import has_permission

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


@router.delete("/employees/{employee_id}/departure")
async def delete_departure(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("hr:manage"))):
    """A scheduled departure called off."""
    from app.services.employee_service import cancel_departure
    try:
        return await cancel_departure(db, current_user.company_id, employee_id)
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


# --- payroll settings (step 2) -------------------------------------------------------------------------------------

@router.get("/payroll/settings")
async def get_settings(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    return await get_payroll_settings(db, current_user.company_id)


@router.put("/payroll/settings")
async def put_settings(payload: PayrollSettingsRequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await update_payroll_settings(db, current_user.company_id, payload.model_dump(exclude_unset=True))
    except EmployeeError as e:
        raise _refused(e)


@router.get("/payroll/irt-tables")
async def get_irt_tables(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    return await list_irt_tables(db, current_user.company_id)


@router.post("/payroll/irt-tables", status_code=status.HTTP_201_CREATED)
async def post_irt_table(payload: IrtTableRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await save_irt_table(db, current_user.company_id, None, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.put("/payroll/irt-tables/{table_id}")
async def put_irt_table(table_id: uuid.UUID, payload: IrtTableRequest, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await save_irt_table(db, current_user.company_id, table_id, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.delete("/payroll/irt-tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_irt_table(table_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        await delete_irt_table(db, current_user.company_id, table_id)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/payroll/items")
async def get_items(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    return await list_items(db, current_user.company_id)


@router.post("/payroll/items", status_code=status.HTTP_201_CREATED)
async def post_item(payload: PayrollItemRequest, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await create_item(db, current_user.company_id, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.put("/payroll/items/{item_id}")
async def put_item(item_id: uuid.UUID, payload: PayrollItemRequest, db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await update_item(db, current_user.company_id, item_id, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.delete("/payroll/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(item_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        await delete_item(db, current_user.company_id, item_id)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/payroll/formula-check")
async def post_formula_check(payload: FormulaCheckRequest, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await check_formula(db, current_user.company_id, payload.formula, payload.code, payload.salary)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/employees/{employee_id}/payroll-items")
async def get_employee_payroll_items(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                     current_user: User = Depends(require_permission("hr:view"))):
    try:
        return await employee_items(db, current_user.company_id, employee_id)
    except EmployeeError as e:
        raise _refused(e)


@router.put("/employees/{employee_id}/payroll-items")
async def put_employee_payroll_items(employee_id: uuid.UUID, payload: EmployeePayrollItemsRequest,
                                     db: AsyncSession = Depends(get_db),
                                     current_user: User = Depends(require_permission("hr:manage"))):
    try:
        return await set_employee_items(db, current_user.company_id, employee_id, payload.items)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/employees/{employee_id}/simulation")
async def post_simulation(employee_id: uuid.UUID, payload: SimulationRequest, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_permission("hr:view"))):
    try:
        return await simulate_payslip(db, current_user.company_id, employee_id, payload.month_values)
    except EmployeeError as e:
        raise _refused(e)


# --- the work calendar and the absence types (step 3a / 3b) -----------------------------------------------------

@router.get("/calendar/holidays")
async def get_holidays(year: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    return await list_holidays(db, current_user.company_id, year)


@router.post("/calendar/holidays/generate")
async def post_generate_holidays(year: int, db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await generate_holidays(db, current_user.company_id, year)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/calendar/holidays", status_code=status.HTTP_201_CREATED)
async def post_holiday(payload: HolidayRequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await save_holiday(db, current_user.company_id, None, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.put("/calendar/holidays/{holiday_id}")
async def put_holiday(holiday_id: uuid.UUID, payload: HolidayRequest, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await save_holiday(db, current_user.company_id, holiday_id, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.delete("/calendar/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_holiday(holiday_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        await delete_holiday(db, current_user.company_id, holiday_id)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/calendar/count")
async def get_count_days(start: date, end: date, working_days: bool = True, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("hr:view"))):
    try:
        return await count_days(db, current_user.company_id, start, end, working_days)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/absence-types")
async def get_absence_types(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    return await list_absence_types(db, current_user.company_id)


@router.post("/absence-types", status_code=status.HTTP_201_CREATED)
async def post_absence_type(payload: AbsenceTypeRequest, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await save_absence_type(db, current_user.company_id, None, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.put("/absence-types/{type_id}")
async def put_absence_type(type_id: uuid.UUID, payload: AbsenceTypeRequest, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        return await save_absence_type(db, current_user.company_id, type_id, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.delete("/absence-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_absence_type(type_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_permission("hr:payroll_settings"))):
    try:
        await delete_absence_type(db, current_user.company_id, type_id)
    except EmployeeError as e:
        raise _refused(e)


# --- the absences (step 3c) -----------------------------------------------------------------------------------------

@router.get("/absences")
async def get_absences(date_from: date | None = None, date_to: date | None = None, status_filter: str | None = None,
                       employee_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("hr:view"))):
    return await list_absences(db, current_user.company_id, date_from, date_to, status_filter, employee_id)


@router.get("/absences/options")
async def get_absence_options(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    return await absence_options(db, current_user.company_id)


@router.get("/absences/map")
async def get_absence_map(year: int, month: int, department_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_permission("hr:view"))):
    try:
        return await month_map(db, current_user.company_id, year, month, department_id)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/absences/{absence_id}")
async def get_absence(absence_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("hr:view"))):
    try:
        return await absence_detail(db, current_user.company_id, absence_id)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/absences", status_code=status.HTTP_201_CREATED)
async def post_absence(payload: AbsenceRequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("hr:absences"))):
    # approved at once only by who may approve
    approve = payload.approve and await has_permission(db, current_user.company_id, current_user.role.value, "hr:absences_approve")
    try:
        return await create_absence(db, current_user.company_id, current_user.id, payload.model_dump(), approve=approve)
    except EmployeeError as e:
        raise _refused(e)


@router.put("/absences/{absence_id}")
async def put_absence(absence_id: uuid.UUID, payload: AbsenceRequest, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("hr:absences"))):
    try:
        return await update_absence(db, current_user.company_id, absence_id, payload.model_dump())
    except EmployeeError as e:
        raise _refused(e)


@router.post("/absences/{absence_id}/approve")
async def post_approve_absence(absence_id: uuid.UUID, payload: AbsenceDecisionRequest, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(require_permission("hr:absences_approve"))):
    try:
        return await approve_absence(db, current_user.company_id, current_user.id, absence_id, payload.note)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/absences/{absence_id}/refuse")
async def post_refuse_absence(absence_id: uuid.UUID, payload: AbsenceDecisionRequest, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_permission("hr:absences_approve"))):
    try:
        return await refuse_absence(db, current_user.company_id, current_user.id, absence_id, payload.note)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/absences/{absence_id}/cancel")
async def post_cancel_absence(absence_id: uuid.UUID, payload: AbsenceDecisionRequest, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_permission("hr:absences_approve"))):
    try:
        return await cancel_absence(db, current_user.company_id, current_user.id, absence_id, payload.note)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/absences/{absence_id}/document")
async def post_absence_document(absence_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("hr:absences"))):
    try:
        content = await _read_upload(file, DOCUMENT_MAX)
        return await attach_document(db, current_user.company_id, current_user.id, absence_id, file.filename, content)
    except EmployeeError as e:
        raise _refused(e)


# --- the holiday balance (step 3d) ----------------------------------------------------------------------------------

@router.get("/vacations")
async def get_vacations(year: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("hr:view"))):
    from app.services.vacation_service import vacation_overview
    try:
        return await vacation_overview(db, current_user.company_id, year)
    except EmployeeError as e:
        raise _refused(e)


@router.get("/vacations/adjustments")
async def get_vacation_adjustments(employee_id: uuid.UUID, year: int, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_permission("hr:view"))):
    from app.services.vacation_service import list_adjustments
    try:
        return await list_adjustments(db, current_user.company_id, employee_id, year)
    except EmployeeError as e:
        raise _refused(e)


@router.post("/vacations/adjustments", status_code=status.HTTP_201_CREATED)
async def post_vacation_adjustment(payload: VacationAdjustmentRequest, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_permission("hr:absences_approve"))):
    from app.services.vacation_service import add_adjustment
    try:
        return await add_adjustment(db, current_user.company_id, current_user.id, payload.employee_id, payload.year,
                                    payload.days, payload.note)
    except EmployeeError as e:
        raise _refused(e)


@router.delete("/vacations/adjustments/{adjustment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vacation_adjustment(adjustment_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                     current_user: User = Depends(require_permission("hr:absences_approve"))):
    from app.services.vacation_service import delete_adjustment
    try:
        await delete_adjustment(db, current_user.company_id, adjustment_id)
    except EmployeeError as e:
        raise _refused(e)
