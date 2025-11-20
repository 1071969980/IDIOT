from typing import Annotated
from uuid import UUID
from fastapi import Body, Depends, HTTPException, status

from api.authentication.utils import _User, get_current_active_user
from api.chat.sql_stat.u2a_session.utils import (
    _U2ASessionUpdate,
    delete_session,
    get_sessions_by_user_id,
    update_session_fields,
)

from .data_model import (
    SessionListResponse,
    SessionMessageHistoryResponseItem,
    SessionResponse,
    UpdateSessionTitleRequest,
    SessionMessageHistoryRequest,
    SessionMessageHistoryResponse,
)
from .router_declare import router

from api.chat.sql_stat.u2a_user_msg.utils import (
    _U2AUserMessage,
    get_user_messages_by_session,
    get_user_messages_by_session_with_limit,
    get_user_messages_by_session_with_limit_and_seq_index,
)

from api.chat.sql_stat.u2a_agent_msg.utils import (
    _U2AAgentMessage,
    get_agent_messages_by_session_task,
)

@router.get("/sessions", response_model=SessionListResponse)
async def get_user_sessions(
    current_user: _User = Depends(get_current_active_user),
) -> SessionListResponse:
    """获取当前用户的所有会话"""
    try:
        sessions = await get_sessions_by_user_id(current_user.id)
        session_responses = [
            SessionResponse(
                id=session.id,
                user_id=session.user_id,
                title=session.title,
                archived=session.archived,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in sessions
        ]

        return SessionListResponse(sessions=session_responses)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取会话列表失败: {e!s}",
        ) from e

@router.post("/sessions/update-title", response_model=dict)
async def update_session_title(
    request: UpdateSessionTitleRequest,
    current_user: _User = Depends(get_current_active_user),
):
    """更新会话标题"""
    try:
        # 首先验证会话是否存在且属于当前用户
        user_sessions = await get_sessions_by_user_id(current_user.id)
        session_exists = any(session.id == request.session_id for session in user_sessions)

        if not session_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在或不属于当前用户",
            )

        # 更新会话标题
        update_data = _U2ASessionUpdate(
            id=request.session_id,
            fields={"title": request.title},
        )

        success = await update_session_fields(update_data)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新会话标题失败",
            )

        return {
            "message": "会话标题更新成功",
            "session_id": request.session_id,
            "new_title": request.title,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新会话标题失败: {e!s}",
        ) from e
    
@router.delete("/delete_session")
async def delete_session_api(
    session_id: Annotated[UUID, Body()],
    current_user: _User = Depends(get_current_active_user),
):
    """删除会话"""
    try:
        # 首先验证会话是否存在且属于当前用户
        user_sessions = await get_sessions_by_user_id(current_user.id)
        session_exists = any(session.id == session_id for session in user_sessions)
        if not session_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在或不属于当前用户",
            )
    
        success = await delete_session(session_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="删除会话失败",
            )
        
        return
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除会话失败: {e!s}",
        ) from e
