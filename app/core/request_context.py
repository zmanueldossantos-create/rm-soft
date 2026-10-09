"""
What a request knows about who makes it, for code far from the route: the authenticated user's id, set by
app.api.deps.get_current_user. A ContextVar is private to each request - two cashiers selling at the same time never
mix. Outside a request (tests, background tasks) it is None.
"""
import uuid
from contextvars import ContextVar

current_user_id: ContextVar[uuid.UUID | None] = ContextVar("current_user_id", default=None)
