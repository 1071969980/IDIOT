"""Publish HIL notification events to the session-level event stream."""

from __future__ import annotations

from uuid import UUID, uuid4

from api.chat.session_streaming.events import (
    HilNotificationEvent,
    HilNotificationEventPayload,
)
from api.chat.session_streaming.writer import publish_session_stream_event

from .data_model import (
    HILNotificationContent,
    HILNotificationContentAgentToolCallBody,
    HILNotificationContentAgentToolCallBodyType,
)


async def notification(
    content: HILNotificationContent,
    *,
    session_id: UUID,
    session_task_id: UUID,
    branch_name: str | None = None,
) -> str:
    """Publish a pending HIL notification and return its interaction msg_id."""
    if not isinstance(content, HILNotificationContent):
        raise ValueError("Invalid content type, should be HILNotificationContent")

    msg_id = str(uuid4())
    event = HilNotificationEvent(
        session_id=session_id,
        session_task_id=session_task_id,
        branch_name=branch_name,
        payload=HilNotificationEventPayload(
            msg_id=msg_id,
            content=content,
        ),
    )
    await publish_session_stream_event(event)
    return msg_id
