"""
Tests for cash_movement_service and its integration with close_session's
expected-amount calculation (see close_session docstring update).

ARCHITECTURE NOTE: this used to test transfers to/from a separate CashOffice
entity. That concept has been retired - every Activity now gets its own
default POS (PointOfSale.is_default=True), so these tests now transfer
between two ordinary POS instead.
"""
import uuid

import pytest

from app.models.point_of_sale import PointOfSale
from app.services.cash_movement_service import (
    create_cash_movement,
    create_cash_movement_reason,
    receive_cash_movement,
    InvalidCashMovementError,
    ReasonDirectionMismatchError,
    SourcePosNotOpenError,
)
from app.services.cash_session_service import open_session, close_session
from app.models.cash_movement import CashMovementType
from app.models.movement_type import MovementDirection


async def _make_second_pos(db, company, activity):
    """A second POS under the same activity, standing in for what used to be the CashOffice in these tests."""
    pos = PointOfSale(company_id=company.id, activity_id=activity.id, name=f"Caixa {uuid.uuid4().hex[:6]}")
    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    return pos


async def test_transfer_out_reduces_expected_amount_on_close(db, company_with_essentials):
    """A cash-out transfer to another POS mid-session must reduce the drawer's expected total."""
    setup = company_with_essentials
    company = setup["company"]
    other_pos = await _make_second_pos(db, company, setup["activity"])

    # The destination side of a transfer must have an open session too (see DestinationPosNotOpenError rule).
    await open_session(db, company.id, other_pos.id, setup["gestor"], opening_amount=0)
    session = await open_session(db, company.id, setup["pos"].id, setup["gestor"], opening_amount=1000)

    await create_cash_movement(
        db, company.id, CashMovementType.TRANSFERENCIA, setup["gestor"], amount=300,
        source_pos_id=setup["pos"].id, destination_pos_id=other_pos.id,
    )

    closed = await close_session(db, company.id, session.id, setup["gestor"].id, closing_amount_counted=700)

    assert float(closed.closing_amount_expected) == 700  # 1000 - 300
    assert float(closed.closing_difference) == 0


async def test_transfer_in_increases_expected_amount_on_close(db, company_with_essentials):
    """Cash received from another POS mid-session must increase the drawer's expected total,
    but only AFTER the receiving POS confirms receipt - see CashMovement.status docstring."""
    setup = company_with_essentials
    company = setup["company"]
    other_pos = await _make_second_pos(db, company, setup["activity"])

    # The source side of a transfer must have an open session too (see SourcePosNotOpenError rule).
    other_session = await open_session(db, company.id, other_pos.id, setup["gestor"], opening_amount=500)

    session = await open_session(db, company.id, setup["pos"].id, setup["gestor"], opening_amount=1000)

    movement = await create_cash_movement(
        db, company.id, CashMovementType.TRANSFERENCIA, setup["gestor"], amount=200,
        source_pos_id=other_pos.id, destination_pos_id=setup["pos"].id,
    )

    await receive_cash_movement(db, company.id, movement.id, setup["pos"].id, setup["gestor"].id)

    closed = await close_session(db, company.id, session.id, setup["gestor"].id, closing_amount_counted=1200)

    assert float(closed.closing_amount_expected) == 1200  # 1000 + 200


async def test_pending_transfer_not_counted_until_received(db, company_with_essentials):
    """An unreceived TRANSFERENCIA must NOT increase the destination POS's expected total on close."""
    setup = company_with_essentials
    company = setup["company"]
    other_pos = await _make_second_pos(db, company, setup["activity"])

    other_session = await open_session(db, company.id, other_pos.id, setup["gestor"], opening_amount=500)
    session = await open_session(db, company.id, setup["pos"].id, setup["gestor"], opening_amount=1000)

    await create_cash_movement(
        db, company.id, CashMovementType.TRANSFERENCIA, setup["gestor"], amount=200,
        source_pos_id=other_pos.id, destination_pos_id=setup["pos"].id,
    )
    # Deliberately NOT calling receive_cash_movement here.

    closed = await close_session(db, company.id, session.id, setup["gestor"].id, closing_amount_counted=1000)

    assert float(closed.closing_amount_expected) == 1000  # unchanged - transfer still pending


async def test_external_saida_requires_reason(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    await open_session(db, company.id, setup["pos"].id, setup["gestor"], opening_amount=0)

    with pytest.raises(InvalidCashMovementError):
        await create_cash_movement(
            db, company.id, CashMovementType.SAIDA_EXTERNA, setup["gestor"], amount=100,
            source_pos_id=setup["pos"].id,
        )


async def test_reason_direction_must_match_movement_type(db, company_with_essentials):
    """A SAIDA-direction reason cannot be used on an ENTRADA_EXTERNA movement."""
    setup = company_with_essentials
    company = setup["company"]

    reason = await create_cash_movement_reason(db, company.id, "Deposito bancario", MovementDirection.SAIDA)

    with pytest.raises(ReasonDirectionMismatchError):
        await create_cash_movement(
            db, company.id, CashMovementType.ENTRADA_EXTERNA, setup["gestor"], amount=100,
            destination_pos_id=setup["pos"].id, reason_id=reason.id,
        )


async def test_transferencia_cannot_have_a_reason(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    other_pos = await _make_second_pos(db, company, setup["activity"])
    await open_session(db, company.id, setup["pos"].id, setup["gestor"], opening_amount=0)

    reason = await create_cash_movement_reason(db, company.id, "Deposito bancario", MovementDirection.SAIDA)

    with pytest.raises(InvalidCashMovementError):
        await create_cash_movement(
            db, company.id, CashMovementType.TRANSFERENCIA, setup["gestor"], amount=100,
            source_pos_id=setup["pos"].id, destination_pos_id=other_pos.id,
            reason_id=reason.id,
        )


async def test_saida_externa_requires_source_pos_to_have_open_session(db, company_with_essentials):
    """Confirms the fix for the 'closed Bar POS with no funds' bug: funds cannot leave a closed drawer."""
    setup = company_with_essentials
    company = setup["company"]
    # No open_session() call here - the POS's register was never opened.

    with pytest.raises(SourcePosNotOpenError):
        await create_cash_movement(
            db, company.id, CashMovementType.SAIDA_EXTERNA, setup["gestor"], amount=100,
            source_pos_id=setup["pos"].id,
            reason_id=(await create_cash_movement_reason(db, company.id, "Perda", MovementDirection.SAIDA)).id,
        )
