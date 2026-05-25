"""
HTTP Worker API路由器
SSE 流式 + POST 响应/确认
"""

from typing import Annotated
from uuid import UUID

import ujson
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api.authentication.utils import get_current_active_user
from api.authentication.sql_stat.utils import _User
from api.chat.sql_stat.u2a_session_task.utils import get_task
from api.human_in_loop.http_worker.long_poll_worker import long_poll_worker
from api.human_in_loop.http_worker.stream_listener import hil_msg_stream_generator

from .data_model import (
    HILResponseRequest,
    HILAckNotificationRequest,
    HILStreamingRequest,
)

# 创建API路由器
router = APIRouter(
    prefix="/hil",
    tags=["human-in-loop-http"]
)


async def _hil_stream_generator(
    session_task_id: UUID,
    last_event_id: str,
):
    """将 HIL stream listener 的输出格式化为 SSE"""
    yield "event:init\nretry:10\n\n"

    async for msg_id, data in hil_msg_stream_generator(
        session_task_id, last_event_id
    ):
        yield (
            f"event:{data['msg_type']}\n"
            f"data:{ujson.dumps(data, ensure_ascii=False)}\n"
            f"id:{msg_id}\n\n"
        )


@router.post("/streaming", response_model=None)
async def hil_streaming(
    request: Request,
    request_param: HILStreamingRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> StreamingResponse:
    """SSE 流式 HIL 消息端点"""

    session_task = await get_task(request_param.session_task_id)
    if session_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话任务不存在",
        )
    if session_task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话任务不属于当前用户",
        )

    last_event_id = request.headers.get("Last-Event-ID") or "0"

    return StreamingResponse(
        _hil_stream_generator(request_param.session_task_id, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/respond")
async def send_response(
    request: HILResponseRequest,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """发送响应端点"""

    try:
        HIL_msg_id = request.hil_msg_id
        msg = request.msg

        success = await long_poll_worker.ack_message(HIL_msg_id, str(request.session_task_id), user.user_name)
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
        await long_poll_worker.send_response_with_params(HIL_msg_id, msg, str(request.session_task_id), user.user_name)
        return
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/ack_notification")
async def ack_notification(
    request: HILAckNotificationRequest,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """确认Notification消息"""
    try:
        success = await long_poll_worker.ack_message(request.hil_msg_id, str(request.session_task_id), user.user_name)
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
        return
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
