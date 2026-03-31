from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from api.authentication.utils import _User, get_current_active_user
from api.chat.sql_stat.u2a_agent_msg.utils import (
    _U2AAgentMessage,
    get_agent_messages_by_session_task_ids,
)
from api.chat.sql_stat.u2a_session.utils import (
    get_session,
)
from api.chat.sql_stat.u2a_session_branch.utils import (
    get_branch_by_session_and_name,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    get_tasks_on_branch_path_until_breakpoint,
)
from api.chat.sql_stat.u2a_user_msg.utils import (
    _U2AUserMessage,
    get_user_messages_by_session_task_ids,
    get_user_messages_by_session_task_ids_with_limit,
    get_user_messages_by_session_task_ids_with_limit_and_seq_index,
)

from .data_model import (
    SessionMessageHistoryRequest,
    SessionMessageHistoryResponse,
    SessionMessageHistoryResponseItem,
)
from .router_declare import router


@router.post("/sessions/messages_history", response_model=SessionMessageHistoryResponse)
async def get_session_messages_history(
    request: SessionMessageHistoryRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
):
    """获取会话消息历史（按分支过滤）"""
    # 首先验证会话是否存在且属于当前用户
    session = await get_session(request.session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或不属于当前用户",
        )

    # 1. 解析 branch → leaf_task_id → 获取 branch path 上的 task 列表
    branch = await get_branch_by_session_and_name(request.session_id, request.branch_name)
    if branch is None:
        return SessionMessageHistoryResponse(
            session_id=request.session_id,
            messages=[],
        )

    task_path = await get_tasks_on_branch_path_until_breakpoint(branch.leaf_task_id)
    if not task_path:
        return SessionMessageHistoryResponse(
            session_id=request.session_id,
            messages=[],
        )

    task_ids = [task.id for task in task_path]

    # 2. 批量查询 branch path 上的 user 消息（仅相关 task）
    if request.limit is not None and request.max_seq_index is not None:
        user_messages = await get_user_messages_by_session_task_ids_with_limit_and_seq_index(
            task_ids,
            request.limit,
            request.max_seq_index,
        )
    elif request.limit is not None:
        user_messages = await get_user_messages_by_session_task_ids_with_limit(
            task_ids,
            request.limit,
        )
    elif request.max_seq_index is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="参数错误: 当限定最大序号时，请提供 limit 参数",
        )
    else:
        user_messages = await get_user_messages_by_session_task_ids(task_ids)

    # 3. 批量查询 branch path 上的 agent 消息（1 次调用替代 N 次）
    agent_messages = await get_agent_messages_by_session_task_ids(task_ids)

    # 4. 按 session_task_id 分组
    grouped_user: dict[UUID, list[_U2AUserMessage]] = {}
    for msg in user_messages:
        grouped_user.setdefault(msg.session_task_id, []).append(msg)

    grouped_agent: dict[UUID, list[_U2AAgentMessage]] = {}
    for msg in agent_messages:
        grouped_agent.setdefault(msg.session_task_id, []).append(msg)

    # limit 情况下消息是 DESC 序，需要重排为 ASC
    for group in grouped_user.values():
        group.sort(key=lambda x: x.seq_index)

    # 5. 按 task_path 的顺序（seq_in_session 升序）合并消息
    res: list[SessionMessageHistoryResponseItem] = []

    for task in task_path:
        if task.id in grouped_user:
            res.extend([
                SessionMessageHistoryResponseItem(
                    role="user",
                    message=mem,
                ) for mem in grouped_user[task.id]
            ])

        if task.id in grouped_agent:
            res.extend([
                SessionMessageHistoryResponseItem(
                    role="assistant",
                    message=mem,
                ) for mem in grouped_agent[task.id]
            ])

    return SessionMessageHistoryResponse(
        session_id=request.session_id,
        messages=res,
    )
