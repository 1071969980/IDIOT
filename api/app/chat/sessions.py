from uuid import UUID
from fastapi import Depends, HTTPException, status

from api.authentication.constant import AUTH_HEADER
from api.authentication.utils import _User, get_current_active_user
from api.chat.sql_stat.u2a_session.utils import (
    _U2ASessionUpdate,
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
    _: str = Depends(AUTH_HEADER),
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
    auth_header: str = Depends(AUTH_HEADER),
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
        )

@router.post("/sessions/messages_history", response_model=SessionMessageHistoryResponse)
async def get_session_messages_history(
    request: SessionMessageHistoryRequest,
    auth_header: str = Depends(AUTH_HEADER),
    current_user: _User = Depends(get_current_active_user),
):
    """获取会话消息历史"""
    # 首先验证会话是否存在且属于当前用户
    user_sessions = await get_sessions_by_user_id(current_user.id)
    session_exists = any(session.id == request.session_id for session in user_sessions)

    if not session_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或不属于当前用户",
        )
    
    # 获取用户会话消息
    if request.limit is not None and request.max_seq_index is not None:
        user_mssages = await get_user_messages_by_session_with_limit_and_seq_index(
            request.session_id,
            request.limit,
            request.max_seq_index,
        )
    elif request.limit is not None:
        user_mssages = await get_user_messages_by_session_with_limit(
            request.session_id,
            request.limit,
        )
    elif request.max_seq_index is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="参数错误: 当限定最大序号时，请提供 limit 参数",
        )
    else:
        user_mssages = await get_user_messages_by_session(request.session_id)

    # 按session_task_id 分组,并每组按 seq_index 进行排序
    grouped_user_mssages : dict[UUID | None, list[_U2AUserMessage]] = {}
    for msg in user_mssages:
        session_task_id = msg.session_task_id
        if session_task_id not in grouped_user_mssages:
            grouped_user_mssages[session_task_id] = []
        grouped_user_mssages[session_task_id].append(msg)
    
    for group in grouped_user_mssages.values():
        group.sort(key=lambda x: x.seq_index)
    
        
    # 计算每个task的最大user记忆seq_index用于排序
    task_max_seq_index = {session_task_id: max(mem.seq_index for mem in mems)
                            for session_task_id, mems in grouped_user_mssages.items()}
    
    # 按照task的user记忆seq_index最大值升序排序（None排在最后）
    sorted_session_task_ids = sorted(
        grouped_user_mssages.keys(),
        key=lambda task_id: task_max_seq_index.get(task_id, float("inf")) if task_id is not None else float("inf")
    )

    res : list[SessionMessageHistoryResponseItem] = []

    for session_task_id in sorted_session_task_ids:
        # 添加该task的user记忆
        if session_task_id in grouped_user_mssages:
            res.extend([
                SessionMessageHistoryResponseItem(
                    role="user",
                    message = mem,
                ) for mem in grouped_user_mssages[session_task_id]
            ])
            # 添加该task的agent记忆
            if session_task_id is not None:
                agent_msgs = await get_agent_messages_by_session_task(session_task_id)
                res.extend([
                    SessionMessageHistoryResponseItem(
                        role="assistant",
                        message = mem,
                    ) for mem in agent_msgs
                ])

    return SessionMessageHistoryResponse(
        session_id=request.session_id,
        messages=res,
    )