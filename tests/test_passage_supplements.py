"""A passage is paid at its Entrada: the time past it is not free. At its exit, the started slices of its rate are
charged (an ordinary paid document) or let go with the reason said; more time while there is bought at once; a
passage is not shortened. The Histórico counts the supplements with it."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.booking_supplement import BookingSupplement
from app.services.hotel_service import (
    InvalidStayStateError, OverstayToSettleError, SupplementPaymentRequiredError, check_out, extend_stay,
    passage_overstay,
)
from app.services.resource_history_service import get_resource_history
from tests.test_hotel_walk_in import _enter, _rooms
from tests.test_hotel_stay import BASE


def _cash(ctx, amount):
    return [{"payment_method_id": ctx["pm_numerario"].id, "amount": amount}]


@pytest.mark.asyncio
async def test_an_excess_is_charged_or_let_go_with_a_reason(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    room, hour, _ = await _rooms(db, ctx)
    booking, _ = await _enter(db, ctx, room, hour, now=BASE)
    late = BASE + timedelta(minutes=87)  # 27 min past the paid hour: one more slice starts
    assert await passage_overstay(db, cid, booking.id, now=late) == {"minutes": 27, "slices": 1}
    assert await passage_overstay(db, cid, booking.id, now=BASE + timedelta(minutes=50)) == {"minutes": 0, "slices": 0}

    from app.models.booking import BookingStatus
    from app.services.booking_service import BookingNotEditableError, update_booking_status
    with pytest.raises(BookingNotEditableError, match="termina com a Saída"):  # no way round the exit
        await update_booking_status(db, cid, booking.id, BookingStatus.CONCLUIDA)
    with pytest.raises(OverstayToSettleError, match="Excedeu 27 min: cobre 1 × Quarto 1 hora"):
        await check_out(db, cid, booking.id, ctx["gestor"], now=late)
    booking = await check_out(db, cid, booking.id, ctx["gestor"], payments=_cash(ctx, 5700.0), pos_id=ctx["pos"].id,
                              now=late)
    [supplement] = (await db.execute(select(BookingSupplement))).scalars().all()
    assert (supplement.kind, supplement.slices, supplement.minutes) == ("EXCESSO", 1, 27) and supplement.invoice_id
    row = (await get_resource_history(db, cid, None, room.id, BASE - timedelta(hours=1), BASE + timedelta(hours=3)))["entries"][0]
    assert row["revenue"] == 11400.0  # the Entrada and its excess
    assert [e["kind"] for e in row["events"]] == ["ENTRADA", "EXCESSO", "SAIDA"]
    assert row["events"][1]["text"] == "Excesso de 27 min - 1 a mais cobrada" and row["events"][1]["amount"] == 5700.0

    # another passage, its excess let go: said why, nothing sold
    second, _ = await _enter(db, ctx, room, hour, now=BASE + timedelta(hours=3))
    await check_out(db, cid, second.id, ctx["gestor"], waive_reason="Cliente habitual", now=BASE + timedelta(hours=4, minutes=10))
    waived = (await db.execute(select(BookingSupplement).where(BookingSupplement.booking_id == second.id))).scalar_one()
    assert waived.invoice_id is None and waived.waived_reason == "Cliente habitual"


@pytest.mark.asyncio
async def test_more_time_on_a_passage_is_paid_at_once(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    room, hour, _ = await _rooms(db, ctx)
    booking, _ = await _enter(db, ctx, room, hour, now=BASE)
    with pytest.raises(SupplementPaymentRequiredError, match="1 × Quarto 1 hora"):
        await extend_stay(db, cid, booking.id, BASE + timedelta(hours=2), user=ctx["gestor"])
    booking = await extend_stay(db, cid, booking.id, BASE + timedelta(hours=2), user=ctx["gestor"],
                                payments=_cash(ctx, 5700.0), pos_id=ctx["pos"].id)
    assert booking.ends_at == BASE + timedelta(hours=2)
    supplement = (await db.execute(select(BookingSupplement))).scalar_one()
    assert (supplement.kind, supplement.slices) == ("PROLONGAMENTO", 1)
    # the same minute as its end (which carries seconds): no change, nothing charged, not «shortened»
    same = await extend_stay(db, cid, booking.id, (booking.ends_at + timedelta(seconds=37)).replace(second=0),
                             user=ctx["gestor"])
    assert same.ends_at == BASE + timedelta(hours=2)
    with pytest.raises(InvalidStayStateError, match="não se encurta"):
        await extend_stay(db, cid, booking.id, BASE + timedelta(hours=1), user=ctx["gestor"])


@pytest.mark.asyncio
async def test_the_life_of_a_stay_in_its_history(db, company_with_essentials):
    """A stay prolonged then shortened: each change of its exit is in its history, with the nights it moved."""
    from tests.test_hotel_stay import _hotel, _stay
    ctx = company_with_essentials
    cid = ctx["company"].id
    room, night, _ = await _hotel(db, ctx)
    booking, _, _ = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=2))
    await extend_stay(db, cid, booking.id, BASE + timedelta(days=3), user=ctx["gestor"])
    await extend_stay(db, cid, booking.id, BASE + timedelta(days=1), user=ctx["gestor"])
    row = (await get_resource_history(db, cid, None, room.id, BASE - timedelta(days=1), BASE + timedelta(days=4)))["entries"][0]
    assert [e["kind"] for e in row["events"]] == ["CHECK_IN", "PROLONGAMENTO", "ENCURTAMENTO"]
    assert row["events"][1]["text"].endswith("(+1)") and row["events"][2]["text"].endswith("(-2)")


@pytest.mark.asyncio
async def test_the_assistant_sees_the_rooms_and_the_bookings(db, company_with_essentials):
    """«Quantos quartos estão ocupados?» - the assistant reads the occupation now and the bookings of a period."""
    from app.services.ai.tools import ocupacao_recursos, reservas
    ctx = company_with_essentials
    cid = ctx["company"].id
    room, hour, _ = await _rooms(db, ctx)
    await _enter(db, ctx, room, hour)
    occupation = await ocupacao_recursos(db, cid, {})
    assert occupation["ocupados"] == 1 and occupation["recursos"][0]["recurso"] == "Quarto 103"
    listed = await reservas(db, cid, {})
    assert [(r["recurso"], r["estado"], r["tarifa"]) for r in listed["reservas"]] == [("Quarto 103", "EM_CURSO", "Quarto 1 hora")]


@pytest.mark.asyncio
async def test_the_assistant_prepares_a_booking_then_makes_it(db, company_with_essentials):
    """«Reserva o Quarto 103 em Diária para amanhã, 2 noites»: checked and priced first, created on confirmation; the
    hours follow the rate; an impossible one (a Pernoite over two nights, a taken room) is refused before asking."""
    import json
    from datetime import date as _date, time as _time
    from app.models.booking import Booking
    from app.models.service import Service
    from app.services.ai.actions import ActionContext, decide_action, run_action_tool
    ctx = company_with_essentials
    cid = ctx["company"].id
    room, _, night = await _rooms(db, ctx)
    db.add(Service(company_id=cid, code="PAS-PER", name="Pernoite", price=10000, vat_id=ctx["vat_nor"].id,
                   unit_of_measure_id=ctx["unit_un"].id, resource_type_id=room.resource_type_id,
                   stay_start_time=_time(22, 0), stay_end_time=_time(7, 30)))
    await db.commit()
    action_ctx = ActionContext(company_id=cid, user_id=ctx["gestor"].id, permissions={"bookings:create"},
                               conversation_id=None, confirm_documents=True, confirm_sends=True)
    day = (_date.today() + timedelta(days=3)).isoformat()
    refused = json.loads(await run_action_tool(db, action_ctx, "preparar_reserva",
                                               {"recurso": "Quarto 103", "tarifa": "Pernoite", "data_entrada": day, "noites": 2}))
    assert "um só período" in refused["erro"]
    answer = json.loads(await run_action_tool(db, action_ctx, "preparar_reserva",
                                              {"recurso": "Quarto 103", "tarifa": "Diária", "data_entrada": day, "noites": 2,
                                               "nome_hospede": "Ana", "pessoas": 2}))
    assert answer["estado"] == "a_aguardar_confirmacao" and answer["resumo"]["total"] == 50000.0
    assert (await db.execute(select(Booking))).scalars().all() == []  # nothing before the confirmation
    action, text = await decide_action(db, cid, ctx["gestor"].id, action_ctx.actions[0], True)
    assert action.status == "FEITA" and "criada" in text
    booking = (await db.execute(select(Booking))).scalar_one()
    assert booking.guest_name == "Ana" and (booking.ends_at - booking.starts_at).days == 2
    taken = json.loads(await run_action_tool(db, action_ctx, "preparar_reserva",
                                             {"recurso": "Quarto 103", "tarifa": "Diária", "data_entrada": day}))
    assert "erro" in taken  # the room is taken those days
