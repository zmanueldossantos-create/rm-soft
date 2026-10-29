"""
Faturação Eletrónica, step D: the contingência. The AGT not answering 3 times (or for 5 minutes) puts the company in
contingência: its new documents take the C series and wait; the first answer of the AGT ends it (the waiting documents
go, in their order) - a contingência switched on by the gestor stays until he switches it off. Without a C series the
N one is used. A document still not validated 18 h after it was issued is reported once.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.document_series import ContingencyIndicator, DocumentSeries
from app.models.invoice import Invoice, InvoiceStatus
from app.services import agt_contingency, agt_queue
from tests.test_agt_documents import YEAR, _issue, _run, agt  # noqa: F401 - the same simulated AGT and company


async def _c_series(db, agt):
    sede = (await db.execute(select(DocumentSeries).where(DocumentSeries.series_code == f"FT{str(YEAR)[2:]}SEDEN"))).scalar_one()
    db.add(DocumentSeries(company_id=sede.company_id, establishment_id=sede.establishment_id,
                          document_type_id=sede.document_type_id, year=YEAR, issuance_mode="ELETRONICA",
                          series_code=f"FT{str(YEAR)[2:]}SEDEC", date_start=sede.date_start, date_end=sede.date_end,
                          agt_status="A", contingency_indicator=ContingencyIndicator.CONTINGENCIA, number_start=1,
                          number_end=999999999, current_number=0))
    await db.commit()


async def test_the_agt_down_switches_to_the_c_series_and_back(db, agt):
    await _c_series(db, agt)
    company_id = agt["company"].id
    first = await _issue(db, agt)
    agt["fake"].down = True
    for minutes in (0, 1, 2):
        await _run(db, minutes=minutes)
    company = await db.get(Company, company_id)
    await db.refresh(company)
    assert company.agt_contingency and not company.agt_contingency_manual and company.agt_net_failures == 3

    during = await _issue(db, agt)  # issued during the outage: on the C series, waiting
    assert during.series == f"FT{str(YEAR)[2:]}SEDEC" and during.number == 1
    view = await agt_contingency.status(db, company)
    assert view["contingency"] and view["has_c_series"] and view["waiting"] == 2

    agt["fake"].down = False
    await _run(db, minutes=30)  # the AGT answers: both sent, in their order, and the contingência ends
    await db.refresh(company)
    assert not company.agt_contingency and company.agt_last_ok_at is not None
    sent = [body["documents"][0]["documentNo"] for service, body in agt["fake"].received if service == "registarFactura"]
    assert sent == [f"FT FT{str(YEAR)[2:]}SEDEN/1", f"FT FT{str(YEAR)[2:]}SEDEC/1"]
    after = await _issue(db, agt)
    assert after.series == f"FT{str(YEAR)[2:]}SEDEN" and after.number == 2
    assert first.id != during.id


async def test_without_a_c_series_the_n_one_is_used(db, agt):
    company = await db.get(Company, agt["company"].id)
    await agt_contingency.set_manual(db, company, True)
    invoice = await _issue(db, agt)
    assert invoice.series == f"FT{str(YEAR)[2:]}SEDEN"
    assert (await agt_contingency.status(db, company))["has_c_series"] is False


async def test_a_manual_contingency_stays_until_the_gestor_ends_it(db, agt):
    company = await db.get(Company, agt["company"].id)
    await agt_contingency.set_manual(db, company, True)
    assert await agt_contingency.note_success(db, company.id) is False  # the AGT answering does not end it
    await db.refresh(company)
    assert company.agt_contingency and company.agt_contingency_manual
    await agt_contingency.set_manual(db, company, False)
    await db.refresh(company)
    assert not company.agt_contingency and company.agt_contingency_since is None


async def test_five_minutes_without_an_answer_is_enough(db, agt):
    company = await db.get(Company, agt["company"].id)
    company.agt_first_failure_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    company.agt_net_failures = 1
    await db.commit()
    assert await agt_contingency.note_failure(db, company.id) is True


async def test_the_18_hours_alert_is_given_once(db, agt):
    invoice = await _issue(db, agt)
    agt["fake"].down = True
    await _run(db)
    invoice.created_at = datetime.now(timezone.utc) - timedelta(hours=19)
    await db.commit()
    company = await db.get(Company, agt["company"].id)
    assert (await agt_contingency.status(db, company))["late"] == 1
    assert await agt_contingency.check_late(db) == 1
    await db.refresh(invoice)
    assert invoice.agt_late_notified_at is not None
    assert await agt_contingency.check_late(db) == 0


async def test_the_gestor_switches_it_from_the_screen(db, agt):
    from app.core.database import get_db
    from app.core.security import create_access_token
    from app.main import app
    from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, agt["company"].id)
    await db.commit()

    async def same():
        yield db
    app.dependency_overrides[get_db] = same
    try:
        h = {"Authorization": "Bearer " + create_access_token(subject=str(agt["gestor"].id),
                                                              company_id=str(agt["company"].id), role="GESTOR")}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            on = (await client.post("/api/v1/company/me/agt/contingency", headers=h, json={"on": True})).json()
            assert on["link"]["contingency"] and on["link"]["manual"] and on["link"]["since"]
            off = (await client.post("/api/v1/company/me/agt/contingency", headers=h, json={"on": False})).json()
            assert not off["link"]["contingency"]
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_the_agt_events_are_offered_only_in_faturacao_eletronica(db, agt):
    from app.services.notification_service import available_events
    company = await db.get(Company, agt["company"].id)
    assert {"AGT_CONTINGENCIA", "AGT_ATRASO"} <= set(await available_events(db, company.id))
    company.issuance_mode = "MANUAL"
    await db.commit()
    assert not {"AGT_CONTINGENCIA", "AGT_ATRASO"} & set(await available_events(db, company.id))
