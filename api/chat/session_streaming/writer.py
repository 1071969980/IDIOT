"""Redis writer for the session-level SSE event bus."""

from __future__ import annotations

from weakref import WeakValueDictionary
from uuid import UUID

import logfire

from api.redis.constants import CLIENT
from api.redis.retry import retry_on_connection_error

from .constants import (
    SESSION_EVENT_STREAM_MAXLEN,
    SESSION_EVENT_STREAM_TTL_SECONDS,
    session_event_stream_key,
)
from .events import (
    HilInterruptRequestEvent,
    HilNotificationEvent,
    SessionStreamEvent,
)
from .hil_state import publish_pending_interaction_event


_SESSION_STREAM_WRITERS: WeakValueDictionary[UUID, "SessionStreamWriter"] = (
    WeakValueDictionary()
)


def _as_str(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


class SessionStreamWriter:
    """Writes all event channels for one session to one Redis Stream."""

    def __init__(self, session_id: UUID):
        self.session_id = session_id

    @property
    def stream_key(self) -> str:
        return session_event_stream_key(self.session_id)

    async def publish(self, event: SessionStreamEvent) -> str:
        """Serialize an event once and write it to the session stream."""
        if event.session_id != self.session_id:
            raise ValueError("event.session_id does not match writer session")

        event_json = event.model_dump_json()

        if isinstance(event, (HilInterruptRequestEvent, HilNotificationEvent)):
            async def _write_hil_event() -> str:
                return await publish_pending_interaction_event(
                    self.session_id,
                    event.payload.msg_id,
                    event_json,
                )

            entry_id = await retry_on_connection_error(
                _write_hil_event,
                operation_name=f"session_stream:hil:{self.stream_key}",
            )
        else:
            async def _write_regular_event() -> object:
                async with CLIENT.pipeline(transaction=True) as pipe:
                    pipe.xadd(
                        self.stream_key,
                        {"event": event_json},
                        maxlen=SESSION_EVENT_STREAM_MAXLEN,
                        approximate=True,
                    )
                    pipe.expire(
                        self.stream_key,
                        SESSION_EVENT_STREAM_TTL_SECONDS,
                    )
                    result = await pipe.execute()
                return result[0]

            entry_id = await retry_on_connection_error(
                _write_regular_event,
                operation_name=f"session_stream:xadd:{self.stream_key}",
            )

        return _as_str(entry_id)


async def publish_session_stream_event(event: SessionStreamEvent) -> str:
    """Publish one event to the stream for ``event.session_id``.

    The writer is cached weakly and only exists for the duration of active
    calls. Errors are propagated after the retry policy is exhausted.
    """
    session_id = event.session_id
    writer = _SESSION_STREAM_WRITERS.get(session_id)
    if writer is None:
        writer = SessionStreamWriter(session_id)
        _SESSION_STREAM_WRITERS[session_id] = writer
    return await writer.publish(event)


async def refresh_session_stream_ttl(session_id: UUID) -> None:
    """Refresh the session stream TTL. Missing streams are not an error."""
    async def _refresh() -> object:
        return await CLIENT.expire(
            session_event_stream_key(session_id),
            SESSION_EVENT_STREAM_TTL_SECONDS,
        )

    try:
        await retry_on_connection_error(
            _refresh,
            operation_name=f"session_stream:expire:{session_event_stream_key(session_id)}",
        )
    except Exception:
        # Heartbeat callers need to keep the HIL wait loop alive even when Redis
        # is briefly unavailable; the failure is visible in logs.
        logfire.error(
            "session_stream: 刷新 TTL 失败",
            session_id=str(session_id),
        )
        raise
