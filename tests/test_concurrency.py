"""
Two tills at the same moment on the shop's network: each document takes its own number (the series row is locked until
the transaction ends) and an AGT step is claimed by one worker only (FOR UPDATE SKIP LOCKED) - never the same document
sent twice. Two real sessions (two connections), like two server processes.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.document_series import DocumentSeries
from app.models.document_type import DocumentType
from app.services.document_series_service import get_next_number


async def _series(db, company_id) -> DocumentSeries:
    doc_type = (await db.execute(select(DocumentType).limit(1))).scalar_one()
    series = DocumentSeries(company_id=company_id, document_type_id=doc_type.id, year=2026, series_code="FR2026T",
                            date_start=date(2026, 1, 1), date_end=date(2026, 12, 31), current_number=7)
    db.add(series)
    await db.commit()
    return series


@pytest.mark.asyncio
async def test_two_tills_never_take_the_same_number(db, company_with_essentials, test_engine):
    series_id = (await _series(db, company_with_essentials["company"].id)).id
    sessions = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as till_a, sessions() as till_b:
        series_a, series_b = await till_a.get(DocumentSeries, series_id), await till_b.get(DocumentSeries, series_id)
        first = await get_next_number(till_a, series_a)
        second_task = asyncio.create_task(get_next_number(till_b, series_b))
        await asyncio.sleep(0.3)
        assert not second_task.done()  # waits for the first till's transaction
        await till_a.commit()
        second = await second_task
        await till_b.commit()
    assert (first, second) == (8, 9)


@pytest.mark.asyncio
async def test_an_agt_step_is_claimed_by_one_worker_only(db, company_with_essentials, test_engine):
    from app.services import agt_queue
    from tests.test_agt_queue import _invoice
    invoice = await _invoice(db, company_with_essentials)
    now = datetime.now(timezone.utc)
    invoice.issuance_mode, invoice.agt_next_attempt_at = "ELETRONICA", now - timedelta(minutes=1)  # due at the AGT
    await db.commit()
    sessions = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as worker_a, sessions() as worker_b:
        assert await agt_queue.claim_due(worker_a, invoice.id, now) is not None
        assert await agt_queue.claim_due(worker_b, invoice.id, now) is None  # locked: the other worker skips it
        await worker_a.rollback()
        invoice_a = await agt_queue.claim_due(worker_a, invoice.id, now)
        invoice_a.agt_next_attempt_at = now + timedelta(minutes=5)  # worker A did the step: the next one is later
        await worker_a.commit()
        assert await agt_queue.claim_due(worker_b, invoice.id, now) is None  # no longer due: never done twice


@pytest.mark.asyncio
async def test_a_singleton_loop_runs_in_one_process_only(test_engine, monkeypatch):
    """Two API processes start the Telegram reader: one runs it, the other waits (and takes over when it stops)."""
    import app.core.database as database
    from app.core import singleton
    monkeypatch.setattr(database, "engine", test_engine)
    running = []

    def loop(name):
        async def run():
            running.append(name)
            await asyncio.sleep(3600)
        return run

    first = asyncio.create_task(singleton.run_singleton("test-loop", loop("a"), retry_seconds=0.2))
    await asyncio.sleep(0.3)
    second = asyncio.create_task(singleton.run_singleton("test-loop", loop("b"), retry_seconds=0.2))
    await asyncio.sleep(0.6)
    assert running == ["a"]  # the second process waits
    first.cancel()  # the first process stops: its lock is freed
    await asyncio.sleep(0.8)
    assert running == ["a", "b"]
    second.cancel()
    await asyncio.gather(first, second, return_exceptions=True)
