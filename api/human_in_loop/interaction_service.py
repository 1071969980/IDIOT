"""Application service for HIL interaction responses and acknowledgements."""

from __future__ import annotations

import json
from uuid import UUID

from api.chat.session_streaming.hil_state import (
    TransitionResult,
    transition_to_acked,
    transition_to_responded,
)


async def respond(
    *,
    session_id: UUID,
    session_task_id: UUID,
    msg_id: str,
    msg: str | dict,
) -> TransitionResult:
    """Atomically convert a pending interrupt to responded and wake its waiter."""
    response_json = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
    return await transition_to_responded(
        session_id,
        session_task_id,
        msg_id,
        response_json,
    )


async def ack_notification(
    *,
    session_id: UUID,
    msg_id: str,
) -> TransitionResult:
    """Atomically convert a pending notification to acked."""
    return await transition_to_acked(session_id, msg_id)
