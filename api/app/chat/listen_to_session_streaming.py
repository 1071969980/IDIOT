from uuid import UUID

from fastapi.responses import StreamingResponse
import ujson
from fastapi import Depends, HTTPException, Request, status

from api.authentication.utils import get_current_active_user
from api.chat.sql_stat.u2a_session.utils import get_session
from api.chat.sql_stat.u2a_session_task.utils import (
    get_task,
)
from api.chat.stream_listener import u2a_msg_stream_generator

from .data_model import (
    ChatStreamingRequset,
)
from .router_declare import router


async def _stream_generator(
        session_task_id: UUID,
        last_event_id: str
):
    # sending init message
    yield "event:init\n\retry:10\n\n"

    # sending main message
    async for t in u2a_msg_stream_generator(
        session_task_id,
        last_event_id
    ):
        if t:
            id, data = t
            yield \
                f"event:{data["type"]}\ndata:{ujson.dumps(data, ensure_ascii=False)}\nid:{id}\n\n"
            
@router.post("/streaming", response_model=None)
async def chat_streaming(
    request: Request,
    request_param: ChatStreamingRequset,
    current_user = Depends(get_current_active_user),
) -> StreamingResponse:
    """
    流式聊天接口
    """
    # 2. 会话存在性验证和所有权验证
    session = await get_session(request_param.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    session_matches_user = session.user_id == current_user.id

    if not session_matches_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不属于当前用户",
        )

    session_task = await get_task(request_param.session_task_id)
    if session_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话任务不存在",
        )
    if session_task.session_id != request_param.session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话任务不属于指定会话",
        )
    if session_task.status != "processing":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话任务未在运行， 任务状态{session_task.status}",
        )
    
    last_event_id = request.headers.get("Last-Event-ID")
    if not last_event_id:
        last_event_id = "0"

    return StreamingResponse(
        _stream_generator(request_param.session_task_id, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )