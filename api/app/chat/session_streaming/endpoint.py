"""Session-level SSE endpoint for Session, Chat, and HIL events."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.authentication.utils import get_current_active_user
from api.chat.sql_stat.u2a_session.utils import get_session
from api.sse_utils import (
    SSE_CURSOR_EXPIRED_FRAME,
    SSE_HEARTBEAT_FRAME,
    iter_with_heartbeat,
)

from .listener import (
    SessionListenerControl,
    SessionStreamRecord,
    session_event_listener,
)
from .router_declare import router


_INIT_FRAME = 'retry:10000\nevent:init\ndata:{"status":"connected"}\n\n'
_VALID_STREAM_ID = re.compile(r"^(?:0|\d+-\d+)$")
_SSE_HEARTBEAT_SECONDS = 15.0


class SessionStreamingRequest(BaseModel):
    session_id: UUID = Field(..., description="会话ID")


def _parse_last_event_id(value: str | None) -> str:
    if value is None:
        return "0"
    if not _VALID_STREAM_ID.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Last-Event-ID 格式非法",
        )
    return value


def _format_event_frame(record: SessionStreamRecord) -> str:
    return (
        f"event:{record.event.channel}.{record.event.type}\n"
        f"data:{record.raw_json}\n"
        f"id:{record.entry_id}\n\n"
    )


async def _stream_generator(session_id: UUID, start_id: str):
    yield _INIT_FRAME

    async for item in iter_with_heartbeat(
        session_event_listener(session_id, start_id),
        heartbeat_interval=_SSE_HEARTBEAT_SECONDS,
    ):
        if item is None:
            yield SSE_HEARTBEAT_FRAME
        elif item is SessionListenerControl.CURSOR_EXPIRED:
            yield SSE_CURSOR_EXPIRED_FRAME
        else:
            yield _format_event_frame(item)


@router.post("/session_streaming", response_model=None)
async def chat_session_streaming(
    request: Request,
    request_param: SessionStreamingRequest,
    current_user=Depends(get_current_active_user),
) -> StreamingResponse:
    """Open the single session-level SSE connection."""
    session = await get_session(request_param.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不属于当前用户",
        )

    start_id = _parse_last_event_id(request.headers.get("Last-Event-ID"))

    return StreamingResponse(
        _stream_generator(request_param.session_id, start_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
