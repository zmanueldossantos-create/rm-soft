"""
Sending one document to the AGT - the single place both queues use (Celery: app/workers/agt_worker.py; the database:
app/services/agt_queue.py).

No real AGT endpoint yet (homologation pending, section 4.4): the round trip is simulated with a realistic delay and a
small failure rate, so the retry and ERRO paths are exercised for real. The real call replaces send_document only.
"""
import asyncio
import random

SIMULATED_FAILURE_RATE = 0.2


class AgtSendError(Exception):
    """A failed submission (network, AGT server) - retried; ERRO once the retries are spent."""


async def send_document(invoice_id: str) -> None:
    """Sends this document to the AGT; raises AgtSendError when it did not go."""
    await asyncio.sleep(3)  # simulated network round trip
    if random.random() < SIMULATED_FAILURE_RATE:
        raise AgtSendError("Falha simulada na comunicação com o servidor da AGT")
