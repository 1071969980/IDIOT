from typing import Annotated
from uuid import UUID
from fastapi import Body, Depends, HTTPException, status

from api.authentication.utils import _User, get_current_active_user
from api.chat.sql_stat.u2a_session.utils import (
    _U2ASessionCreate,
    _U2ASessionUpdate,
    delete_session,
    get_sessions_by_created_by,
    get_sessions_by_user_id,
    get_latest_session_by_created_by,
    insert_session,
    update_session_fields,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    get_tasks_by_session,
    get_tasks_by_session_and_status,
)

from .data_model import (
    CreateSessionRequest,
    CreateSessionResponse,
    SessionListResponse,
    SessionMessageHistoryResponseItem,
    SessionResponse,
    UpdateSessionTitleRequest,
    SessionMessageHistoryRequest,
    SessionMessageHistoryResponse,
    GetActiveTaskRequest,
    GetActiveTaskResponse,
    ActiveTaskInfo,
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
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> SessionListResponse:
    """获取当前用户的所有会话"""
    try:
        sessions = await get_sessions_by_created_by(current_user.id, "user")
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


@router.post("/sessions/create", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> CreateSessionResponse:
    """创建会话

    检查用户最新创建的会话（created_by="user"），如果该会话没有消息则返回该会话，否则创建新会话。
    """
    try:
        # 获取用户最新的 created_by="user" 的会话
        latest_session = await get_latest_session_by_created_by(
            current_user.id, "user"
        )

        if latest_session is not None:
            # 检查该会话是否有用户消息
            messages = await get_user_messages_by_session_with_limit(
                latest_session.id, 1
            )
            if len(messages) == 0:
                # 没有消息，返回该会话
                return CreateSessionResponse(
                    session_uuid=latest_session.id,
                    created_new_session=False,
                    message="会话获取成功",
                )

        # 创建新会话
        session_data = _U2ASessionCreate(
            user_id=current_user.id,
            title=request.title,
            created_by="user",
        )
        new_session_id = await insert_session(session_data)

        return CreateSessionResponse(
            session_uuid=new_session_id,
            created_new_session=True,
            message="会话创建成功",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建会话失败: {e!s}",
        ) from e


@router.post("/sessions/active_task", response_model=GetActiveTaskResponse)
async def get_session_active_task(
    request: GetActiveTaskRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> GetActiveTaskResponse:
    """获取指定会话的活跃任务"""
    try:
        # 首先验证会话是否存在且属于当前用户
        user_sessions = await get_sessions_by_user_id(current_user.id)
        session_exists = any(session.id == request.session_id for session in user_sessions)

        if not session_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在或不属于当前用户",
            )

        # 获取活跃任务（pending 或 processing 状态）
        pending_tasks = await get_tasks_by_session_and_status(
            request.session_id, "pending"
        )
        processing_tasks = await get_tasks_by_session_and_status(
            request.session_id, "processing"
        )

        all_active_tasks = pending_tasks + processing_tasks

        # 构建任务信息
        active_task_infos = [
            ActiveTaskInfo(
                id=task.id,
                status=task.status,  # type: ignore
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            for task in all_active_tasks
        ]

        return GetActiveTaskResponse(
            session_id=request.session_id,
            has_active_task=bool(active_task_infos),
            active_tasks=active_task_infos,
            total_count=len(active_task_infos),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取活跃任务失败: {e!s}",
        ) from e

@router.post("/sessions/update_title", response_model=dict)
async def update_session_title(
    request: UpdateSessionTitleRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
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
    current_user: Annotated[_User, Depends(get_current_active_user)],
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
