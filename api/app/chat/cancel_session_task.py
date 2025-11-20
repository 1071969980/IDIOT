from api.authentication.utils import get_current_active_user
from api.chat.sql_stat.u2a_session.utils import get_session
from api.chat.sql_stat.u2a_session_task.utils import get_task
from api.redis.pubsub import publish_event
from .router_declare import router
from .data_model import CancelSessionTaskRequest
from fastapi import Depends, HTTPException, status


@router.post("/cancel_session_task", response_model=None)
async def cancel_session_task(
    request_param: CancelSessionTaskRequest,
    current_user = Depends(get_current_active_user),
):
    # 会话存在性验证和所有权验证
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
    
    await publish_event(f"session_task_canceling:{request_param.session_task_id}")
