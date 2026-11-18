"""Recursos Humanos (capability HR), step 1: the employee's file (matrícula proposed, required fields, dates, IBAN,
uniqueness per company), a departure and a readmission, and the company's HR tables (starting set, rename, switch
off, never deleted once used); the module sells alone (no activity) and the role RH gets its rights."""
import uuid
from datetime import date, timedelta

import pytest

from app.core.capabilities import SECTORS_BY_CODE, capability_of_permission
from app.models.employee import HrReference
from app.models.user import UserRole
from app.services.employee_service import (
    EmployeeError, _iban_ok, create_employee, create_reference, delete_reference, employee_options, list_employees,
    list_references, readmit_employee, register_departure, update_employee, update_reference,
)
from app.services.permission_service import EDITABLE_ROLES, PERMISSION_CATALOG

IBAN = "AO06004000000123456789027"  # a valid Angolan IBAN (check digits 06)


def _file(**extra):
    return {"full_name": "Maria  Fernanda Lopes", "hired_on": date(2024, 3, 1), "base_salary": 180000,
            "payment_method": "TRANSFERENCIA", "iban": "AO06 0040 0000 0123 4567 8902 7", **extra}


def test_the_module_and_the_role():
    sector = SECTORS_BY_CODE["RH"]
    assert sector.ready and not sector.sells and sector.capabilities == ("HR",)
    assert {capability_of_permission(c) for c in ("hr:view", "hr:manage", "hr:settings", "hr:payroll_settings")} == {"HR"}
    assert UserRole("RH") and "RH" in EDITABLE_ROLES
    rh = {code for code, _, _, roles in PERMISSION_CATALOG if "RH" in roles}
    assert rh == {"hr:view", "hr:manage", "hr:settings", "hr:payroll_settings", "hr:absences", "hr:absences_approve"}


def test_iban_check_digits():
    assert _iban_ok(IBAN)
    assert not _iban_ok("AO06004000000123456789028")  # one digit wrong
    assert not _iban_ok("AO0600400000012345678902")  # one digit missing


@pytest.mark.asyncio
async def test_a_file_from_its_creation_to_a_readmission(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id

    options = await employee_options(db, company_id)
    assert options["next_number"] == "0001"
    assert "Por tempo indeterminado" in [t["name"] for t in options["tables"]["TIPO_CONTRATO"]]
    contract = options["tables"]["TIPO_CONTRATO"][0]["id"]

    maria = await create_employee(db, company_id, user_id, _file(contract_type_id=contract, nif="123 456 789 la0"))
    assert maria["number"] == "0001" and maria["full_name"] == "Maria Fernanda Lopes"
    assert maria["iban"] == IBAN and maria["nif"] == "123456789LA0" and maria["contract_type"] == "Por tempo indeterminado"
    assert (await employee_options(db, company_id))["next_number"] == "0002"
    own = await create_employee(db, company_id, user_id, _file(full_name="João Pedro", number="A-17", payment_method="NUMERARIO", iban=None))
    assert own["number"] == "A-17"
    third = await create_employee(db, company_id, user_id, _file(full_name="Ana Silva", payment_method="NUMERARIO", iban=None))
    assert third["number"] == "0002"  # the highest numeric matrícula + 1

    changed = await update_employee(db, company_id, maria["id"], {**_file(), "number": "0001", "base_salary": 200000})
    assert changed["base_salary"] == 200000.0

    gone = await register_departure(db, company_id, maria["id"], date(2026, 6, 30), "DEMISSAO")
    assert not gone["is_active"] and gone["leaving_reason_label"].startswith("Demissão")
    listing = await list_employees(db, company_id)
    assert [e["full_name"] for e in listing["employees"]] == ["Ana Silva", "João Pedro"]
    assert listing["counts"] == {"ATIVOS": 2, "SAIDOS": 1, "TODOS": 3}
    assert [e["number"] for e in (await list_employees(db, company_id, "SAIDOS"))["employees"]] == ["0001"]
    assert len((await list_employees(db, company_id, "TODOS", search="lopes"))["employees"]) == 1

    with pytest.raises(EmployeeError, match="posterior à data de saída"):
        await readmit_employee(db, company_id, maria["id"], date(2026, 6, 30))
    back = await readmit_employee(db, company_id, maria["id"], date(2026, 9, 1))
    assert back["is_active"] and back["hired_on"] == date(2026, 9, 1) and back["left_on"] is None


@pytest.mark.asyncio
async def test_what_a_file_refuses(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    await create_employee(db, company_id, user_id, _file(id_document_number="004567891LA042", social_security_number="12345"))

    for data, message in (
        ({"full_name": " "}, "nome completo"),
        ({"hired_on": None}, "data de admissão"),
        ({"base_salary": 0}, "salário base"),
        ({"iban": None}, "precisa do IBAN"),
        ({"iban": "AO06004000000123456789028"}, "IBAN inválido"),
        ({"birth_date": date.today()}, "anterior a hoje"),
        ({"contract_ends_on": date(2024, 1, 1)}, "anterior à data de admissão"),
        ({"id_issued_on": date(2025, 1, 1), "id_expires_on": date(2024, 1, 1)}, "anterior à data de emissão"),
        ({"email": "maria@"}, "Email inválido"),
        ({"number": "0001"}, "já tem a matrícula 0001"),
        ({"id_document_number": "004567891la042"}, "já tem o documento"),
        ({"social_security_number": "12345"}, "segurança social"),
        ({"department_id": uuid.uuid4()}, "Departamentos: valor inválido"),
    ):
        with pytest.raises(EmployeeError, match=message):
            await create_employee(db, company_id, user_id, {**_file(full_name="Outra Pessoa"), **data})

    with pytest.raises(EmployeeError, match="Descreva"):
        employees = (await list_employees(db, company_id))["employees"]
        await register_departure(db, company_id, employees[0]["id"], date(2026, 1, 31), "OUTRO")


@pytest.mark.asyncio
async def test_the_hr_tables(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    tables = {k["kind"]: k for k in (await list_references(db, company_id))["kinds"]}
    assert tables["DEPARTAMENTO"]["values"] == []  # the company's own
    assert len(tables["ESCOLARIDADE"]["values"]) == 7
    await list_references(db, company_id)  # the starting set is given once
    assert len({k["kind"]: k for k in (await list_references(db, company_id))["kinds"]}["ESCOLARIDADE"]["values"]) == 7

    kitchen = await create_reference(db, company_id, "DEPARTAMENTO", "  Cozinha ")
    assert kitchen["name"] == "Cozinha"
    with pytest.raises(EmployeeError, match="já existe"):
        await create_reference(db, company_id, "DEPARTAMENTO", "cozinha")
    store = await create_reference(db, company_id, "DEPARTAMENTO", "Loja")
    await delete_reference(db, company_id, store["id"])  # unused: deleted

    cook = await create_employee(db, company_id, user_id, _file(department_id=kitchen["id"]))
    assert cook["department"] == "Cozinha"
    with pytest.raises(EmployeeError, match="desative-o"):
        await delete_reference(db, company_id, kitchen["id"])
    await update_reference(db, company_id, kitchen["id"], "Cozinha central", False)
    used = {k["kind"]: k for k in (await list_references(db, company_id))["kinds"]}["DEPARTAMENTO"]["values"]
    assert used[0]["employees"] == 1 and not used[0]["is_active"]
    # the file keeps its switched-off value; a new file cannot take it
    kept = await update_employee(db, company_id, cook["id"], _file(number=cook["number"], department_id=kitchen["id"]))
    assert kept["department"] == "Cozinha central"
    with pytest.raises(EmployeeError, match="desativado"):
        await create_employee(db, company_id, user_id, _file(full_name="Novo", department_id=kitchen["id"]))


@pytest.mark.asyncio
async def test_each_company_has_its_own_files(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    await create_employee(db, company_id, user_id, _file())
    other = uuid.uuid4()
    assert (await list_employees(db, other))["employees"] == []
    other_ref = HrReference(company_id=company_id, kind="FUNCAO", name="Padeiro")
    db.add(other_ref)
    await db.commit()
    # a value of another list is refused
    with pytest.raises(EmployeeError, match="Departamentos: valor inválido"):
        await create_employee(db, company_id, user_id, _file(full_name="Outro", department_id=other_ref.id))


# --- the photo, the documents, the user account, the PDF ------------------------------------------------------------

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n%fake\n"


@pytest.mark.asyncio
async def test_the_photo_and_the_documents(db, company_with_essentials):
    from app.services.employee_file_service import (
        add_document, delete_document, get_document_file, get_photo, list_documents, set_photo,
    )
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    maria = await create_employee(db, company_id, user_id, _file())

    with pytest.raises(EmployeeError, match="JPEG, PNG ou WebP"):
        await set_photo(db, company_id, user_id, maria["id"], "foto.png", PDF)  # the name lies: the bytes decide
    await set_photo(db, company_id, user_id, maria["id"], "foto.png", PNG)
    await set_photo(db, company_id, user_id, maria["id"], "nova.png", PNG + b"1")  # replaces the first
    assert (await get_photo(db, company_id, maria["id"])) == (PNG + b"1", "image/png")
    assert (await list_employees(db, company_id))["employees"][0]["has_photo"]

    docs = await list_documents(db, company_id, maria["id"])
    bi = next(item for item in docs["checklist"] if item["name"] == "Bilhete de identidade")
    assert not bi["delivered"] and docs["documents"] == []
    scanned = await add_document(db, company_id, user_id, maria["id"], bi["document_type_id"], None, date(2024, 3, 1),
                                 date(2030, 1, 1), "C:\\scans\\bi maria.pdf", PDF)
    assert scanned["name"] == "Bilhete de identidade" and scanned["has_file"] and scanned["file_name"] == "bi maria.pdf"
    paper = await add_document(db, company_id, user_id, maria["id"], None, "Declaração de residência", date(2024, 3, 1), None)
    assert not paper["has_file"]
    docs = await list_documents(db, company_id, maria["id"])
    assert len(docs["documents"]) == 2
    assert next(item for item in docs["checklist"] if item["name"] == "Bilhete de identidade")["delivered"]
    assert (await get_document_file(db, company_id, maria["id"], scanned["id"]))[:2] == (PDF, "application/pdf")
    with pytest.raises(EmployeeError, match="em papel"):
        await get_document_file(db, company_id, maria["id"], paper["id"])

    for args, message in (
        ((None, None, None, None), "tipo de documento"),
        ((None, "X", date.today() + timedelta(days=1), None), "futura"),
        ((None, "X", date(2024, 3, 1), date(2024, 1, 1)), "anterior à data de entrega"),
        ((None, "X", None, None, "a.exe", b"MZ\x90\x00"), "PDF ou uma imagem"),
    ):
        with pytest.raises(EmployeeError, match=message):
            await add_document(db, company_id, user_id, maria["id"], *args)
    await delete_document(db, company_id, maria["id"], paper["id"])
    assert len((await list_documents(db, company_id, maria["id"]))["documents"]) == 1

    # nobody else's
    with pytest.raises(EmployeeError):
        await get_document_file(db, uuid.uuid4(), maria["id"], scanned["id"])

    from app.utils.employee_pdf import generate_employee_pdf
    from app.services.employee_service import employee_detail
    pdf = generate_employee_pdf(await employee_detail(db, company_id, maria["id"]), await list_documents(db, company_id, maria["id"]),
                                None, {"name": "Empresa", "nif": "5000000000"})
    assert pdf.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_the_account_closes_with_the_departure(db, company_with_essentials):
    from app.core.security import hash_password
    from app.models.user import User
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    cashier = User(company_id=company_id, full_name="Joana Caixa", phone_number="+244923" + uuid.uuid4().hex[:6].translate(str.maketrans("abcdef", "123456")),
                   password_hash=hash_password("Teste@2026"), role=UserRole.CAIXA)
    db.add(cashier)
    await db.commit()
    cashier_id = cashier.id

    users = (await employee_options(db, company_id))["users"]
    assert {u["id"] for u in users} >= {cashier_id, user_id}
    joana = await create_employee(db, company_id, user_id, _file(full_name="Joana Mendes", user_id=cashier_id))
    assert joana["user_name"] == "Joana Caixa"
    with pytest.raises(EmployeeError, match="já está ligada a Joana Mendes"):
        await create_employee(db, company_id, user_id, _file(full_name="Outra", user_id=cashier_id))
    with pytest.raises(EmployeeError, match="Conta de utilizador inválida"):
        await create_employee(db, company_id, user_id, _file(full_name="Outra", user_id=uuid.uuid4()))

    gone = await register_departure(db, company_id, joana["id"], date(2026, 6, 30), "FIM_CONTRATO")
    assert gone["account_closed"]
    await db.refresh(cashier)
    assert not cashier.is_active
    back = await readmit_employee(db, company_id, joana["id"], date(2026, 8, 1))
    await db.refresh(cashier)
    assert back["is_active"] and not cashier.is_active  # the gestor switches the account back on himself

    # the gestor's own account is never closed (the company would be locked out)
    boss = await create_employee(db, company_id, user_id, _file(full_name="O Gestor", user_id=user_id))
    assert not (await register_departure(db, company_id, boss["id"], date(2026, 6, 30), "OUTRO", "Vendeu a empresa"))["account_closed"]
