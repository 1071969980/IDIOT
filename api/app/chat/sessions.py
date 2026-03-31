from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from api.authentication.utils import _User, get_current_active_user
from api.chat.sql_stat.u2a_session.utils import (
    _U2ASessionCreate,
    _U2ASessionUpdate,
    delete_sessions,
    get_sessions_by_created_by,
    get_sessions_by_user_id,
    get_latest_session_by_created_by,
    insert_session,
    update_session_fields,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    get_tasks_by_session_and_status,
)
from api.chat.sql_stat.u2a_session_branch.utils import (
    get_branch_by_session_and_name,
    get_branches_by_session,
)

from .data_model import (
    CreateSessionRequest,
    CreateSessionResponse,
    SessionListResponse,
    SessionResponse,
    UpdateSessionTitleRequest,
    GetActiveTaskRequest,
    GetActiveTaskResponse,
    ActiveTaskInfo,
    DeleteSessionRequest,
    DeleteSessionResponse,
    DeleteSessionResult,
)
from .router_declare import router

from api.chat.sql_stat.u2a_user_msg.utils import (
    get_user_messages_by_session_with_limit,
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

        # 加载 session 所有分支，构建 branch_id → name 映射
        branches = await get_branches_by_session(request.session_id)
        branch_id_to_name: dict[UUID | None, str | None] = {b.id: b.name for b in branches}
        branch_id_to_name[None] = None

        # 如果指定了 branch_name，按分支过滤
        if request.branch_name is not None:
            branch = await get_branch_by_session_and_name(
                request.session_id, request.branch_name
            )
            if branch is not None:
                target_branch_id = branch.id
                all_active_tasks = [
                    t for t in all_active_tasks if t.branch_id == target_branch_id
                ]
            else:
                all_active_tasks = []

        # 构建任务信息
        active_task_infos = [
            ActiveTaskInfo(
                id=task.id,
                status=task.status,  # type: ignore
                branch_id=task.branch_id,
                branch_name=branch_id_to_name.get(task.branch_id),
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
    
@router.post("/delete_session", response_model=DeleteSessionResponse)
async def delete_session_api(
    request: DeleteSessionRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> DeleteSessionResponse:
    """批量删除会话

    验证所有会话是否属于当前用户，返回每个会话的删除结果详情。
    """
    session_ids = request.session_ids
    results: list[DeleteSessionResult] = []

    try:
        # 获取用户所有会话以验证权限
        user_sessions = await get_sessions_by_user_id(current_user.id)
        user_session_ids = {session.id for session in user_sessions}

        # 分类会话：属于用户 vs 不属于用户
        valid_session_ids: list[UUID] = []
        for session_id in session_ids:
            if session_id in user_session_ids:
                valid_session_ids.append(session_id)
            else:
                results.append(DeleteSessionResult(
                    session_id=session_id,
                    success=False,
                    reason="会话不存在或不属于当前用户",
                ))

        # 批量删除有效的会话
        if valid_session_ids:
            deleted_count = await delete_sessions(valid_session_ids)

            # 根据删除结果构建响应
            # 注意：delete_sessions 返回成功删除的数量，无法精确匹配哪个被删除
            # 所以我们需要重新查询来确认哪些实际被删除了
            remaining_sessions = await get_sessions_by_user_id(current_user.id)
            remaining_session_ids = {session.id for session in remaining_sessions}

            for session_id in valid_session_ids:
                if session_id not in remaining_session_ids:
                    results.append(DeleteSessionResult(
                        session_id=session_id,
                        success=True,
                        reason=None,
                    ))
                else:
                    results.append(DeleteSessionResult(
                        session_id=session_id,
                        success=False,
                        reason="删除失败",
                    ))

        # 统计结果
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count

        return DeleteSessionResponse(
            total_requested=len(session_ids),
            deleted_count=success_count,
            failed_count=failed_count,
            results=results,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除会话失败: {e!s}",
        ) from e
