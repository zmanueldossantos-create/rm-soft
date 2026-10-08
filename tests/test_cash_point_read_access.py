"""Reading a till: a CAIXA reads the sessions, the closing report and the journal of his own till only - another
till answers 403, as does any till for a CAIXA with none assigned. The manager reads every till."""
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.pos import routes as pos_routes
from app.api.v1.tesouraria import routes as tesouraria_routes
from app.models.point_of_sale import PointOfSale
from app.models.user import User, UserRole
from app.services.cash_session_service import close_session, open_session
from app.services.user_cash_point_access_service import assign_user_to_cash_point


async def _closed_session(db, company_id, pos_id, gestor):
    session = await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    return await close_session(db, company_id, session.id, gestor.id, closing_amount_counted=0)


@pytest.mark.asyncio
async def test_a_cashier_reads_his_own_till_only(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, gestor, own_pos = ctx["company"].id, ctx["gestor"], ctx["pos"]
    other = PointOfSale(company_id=company_id, activity_id=ctx["activity"].id, name=f"Caixa {uuid.uuid4().hex[:6]}")
    cashier = User(company_id=company_id, full_name="Caixa Teste", phone_number="+2449" + str(uuid.uuid4().int)[:8],
                   password_hash="x", role=UserRole.CAIXA)
    db.add_all([other, cashier])
    await db.commit()
    await assign_user_to_cash_point(db, company_id, cashier.id, own_pos.id)
    own_session = await _closed_session(db, company_id, own_pos.id, gestor)
    other_session = await _closed_session(db, company_id, other.id, gestor)
    day_from, day_to = own_session.business_date - timedelta(days=1), own_session.business_date + timedelta(days=1)

    # his own till: sessions, closing report, journal
    sessions = await pos_routes.get_sessions(activity_id=None, pos_id=None, db=db, current_user=cashier)
    assert sessions and all(s.pos_id == own_pos.id for s in sessions)
    report = await pos_routes.get_closing_report(session_id=own_session.id, db=db, current_user=cashier)
    assert report.media_type == "application/pdf"
    assert isinstance(await tesouraria_routes.get_pos_daily_report(
        pos_id=own_pos.id, date_from=day_from, date_to=day_to, db=db, current_user=cashier), list)

    assert await pos_routes.get_carry_forward(pos_id=own_pos.id, db=db, current_user=cashier) is not None
    assert await pos_routes.get_current_open_session(pos_id=own_pos.id, db=db, current_user=cashier) is None

    # another till: refused everywhere
    for call in (
        pos_routes.get_current_open_session(pos_id=other.id, db=db, current_user=cashier),
        pos_routes.get_carry_forward(pos_id=other.id, db=db, current_user=cashier),
        pos_routes.get_sessions(activity_id=None, pos_id=other.id, db=db, current_user=cashier),
        pos_routes.get_closing_report(session_id=other_session.id, db=db, current_user=cashier),
        pos_routes.get_current_balance(pos_id=other.id, db=db, current_user=cashier),
        tesouraria_routes.get_pos_daily_report(pos_id=other.id, date_from=day_from, date_to=day_to, db=db, current_user=cashier),
        tesouraria_routes.get_pos_daily_report_pdf(pos_id=other.id, date_from=day_from, date_to=day_to, db=db, current_user=cashier),
    ):
        with pytest.raises(HTTPException) as refused:
            await call
        assert refused.value.status_code == 403

    # the manager reads every till
    assert await pos_routes.get_sessions(activity_id=None, pos_id=other.id, db=db, current_user=gestor)

    # a cashier with no till assigned reads none
    stranger = SimpleNamespace(id=uuid.uuid4(), company_id=company_id, role=UserRole.CAIXA)
    with pytest.raises(HTTPException) as refused:
        await pos_routes.get_sessions(activity_id=None, pos_id=None, db=db, current_user=stranger)
    assert refused.value.status_code == 403
