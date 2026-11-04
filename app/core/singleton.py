"""
One loop for the whole server, however many processes run it. The API runs in several worker processes (uvicorn
--workers, API_WORKERS): a loop that must exist only once - the Telegram bot's reader (Telegram hands a bot's messages
to one reader only), the relay agent - runs in the process that holds its PostgreSQL advisory lock. The others wait
and take over within a minute if that process stops (its connection closes, the lock is freed).
"""
import asyncio
import logging
import zlib
from collections.abc import Awaitable, Callable

from sqlalchemy import text

log = logging.getLogger(__name__)
RETRY_SECONDS = 60


def _key(name: str) -> int:
    return zlib.crc32(("rmsoft:" + name).encode())  # a stable 32-bit key per loop


async def run_singleton(name: str, loop: Callable[[], Awaitable[None]], retry_seconds: float = RETRY_SECONDS) -> None:
    """Runs loop() (a coroutine that runs forever) only while this process holds the lock named name."""
    from app.core.database import engine
    key = _key(name)
    while True:
        try:
            async with engine.connect() as conn:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")  # never idle in a transaction
                if await conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}):
                    log.info("%s: this process runs it", name)
                    try:
                        await loop()
                    finally:
                        await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the database away for a moment: try again later
            log.exception("%s: singleton supervisor failed", name)
        await asyncio.sleep(retry_seconds)
