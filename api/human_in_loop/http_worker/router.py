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
from api.human_in_loop.interaction_service import ack_notification as ack_notification_service
from api.human_in_loop.interaction_service import respond as respond_service
from api.chat.session_streaming.hil_state import TransitionResult
from api.human_in_loop.http_worker.stream_listener import hil_msg_stream_generator
from api.sse_utils import SSE_HEARTBEAT_FRAME, iter_with_heartbeat

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
    yield 'retry:10000\nevent:init\ndata:{"status":"connected"}\n\n'

    async for item in iter_with_heartbeat(
        hil_msg_stream_generator(session_task_id, last_event_id)
    ):
        if item is None:
            yield SSE_HEARTBEAT_FRAME
            continue

        msg_id, data = item
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


async def _get_owned_task(session_task_id: UUID, user_id: UUID):
    session_task = await get_task(session_task_id)
    if session_task is None or session_task.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话任务不存在",
        )
    return session_task


def _transition_http_error(result: TransitionResult) -> None:
    if result is TransitionResult.NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="交互消息不存在或已过期",
        )
    if result is TransitionResult.CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="交互消息已处理",
        )


@router.post("/respond")
async def send_response(
    request: HILResponseRequest,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """发送响应端点"""
    try:
        session_task = await _get_owned_task(request.session_task_id, user.id)
        result = await respond_service(
            session_id=session_task.session_id,
            session_task_id=session_task.id,
            msg_id=request.hil_msg_id,
            msg=request.msg,
        )
        _transition_http_error(result)
        return
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/ack_notification")
async def ack_notification(
    request: HILAckNotificationRequest,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """确认Notification消息"""
    try:
        session_task = await _get_owned_task(request.session_task_id, user.id)
        result = await ack_notification_service(
            session_id=session_task.session_id,
            msg_id=request.hil_msg_id,
        )
        _transition_http_error(result)
        return
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
