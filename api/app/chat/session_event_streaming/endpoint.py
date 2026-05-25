from uuid import UUID

import ujson
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.authentication.utils import get_current_active_user
from api.chat.sql_stat.u2a_session.utils import get_session

from .listener import session_event_listener
from .router_declare import router


class SessionEventStreamingRequest(BaseModel):
    session_id: UUID = Field(..., description="会话ID")


async def _stream_generator(session_id: UUID):
    # SSE init 消息
    yield "event:init\nretry:10\n\n"

    async for event_type, data, event_id in session_event_listener(session_id):
        yield (
            f"event:{event_type}\n"
            f"data:{ujson.dumps(data, ensure_ascii=False)}\n"
            f"id:{event_id}\n\n"
        )


@router.post("/streaming", response_model=None)
async def session_event_streaming(
    request_param: SessionEventStreamingRequest,
    current_user=Depends(get_current_active_user),
) -> StreamingResponse:
    """
    会话事件流式推送 SSE 端点。
    """
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

    return StreamingResponse(
        _stream_generator(request_param.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
