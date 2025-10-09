from fastapi import Depends, HTTPException, status

from api.authentication.constant import AUTH_HEADER
from api.authentication.data_model import UserModel
from api.authentication.utils import get_current_active_user
from api.chat.sql_stat.u2a_session.utils import (
    _U2ASessionUpdate,
    get_sessions_by_user_id,
    update_session_fields,
)

from .data_model import (
    SessionListResponse,
    SessionResponse,
    UpdateSessionTitleRequest,
)
from .router_declare import router


@router.get("/sessions", response_model=SessionListResponse)
async def get_user_sessions(
    current_user: UserModel = Depends(get_current_active_user),
    _: str = Depends(AUTH_HEADER),
) -> SessionListResponse:
    """获取当前用户的所有会话"""
    try:
        sessions = await get_sessions_by_user_id(current_user.uuid)
        session_responses = [
            SessionResponse(
                id=session.id,
                user_id=session.user_id,
                session_id=session.session_id,
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
    auth_header: str = Depends(AUTH_HEADER),
    current_user: UserModel = Depends(get_current_active_user),
):
    """更新会话标题"""
    try:
        # 首先验证会话是否存在且属于当前用户
        user_sessions = await get_sessions_by_user_id(current_user.uuid)
        session_exists = any(session.session_id == request.session_id for session in user_sessions)

        if not session_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在或不属于当前用户",
            )

        # 更新会话标题
        update_data = _U2ASessionUpdate(
            session_id=request.session_id,
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
        )

