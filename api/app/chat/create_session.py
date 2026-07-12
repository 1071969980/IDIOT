from typing import Annotated

from fastapi import Depends, HTTPException, status

from api.agent.session_agent_config.constants import DEFAULT_MAIN_AGENT_SESSION_CONFIG
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    insert_session_config,
    _U2ASessionAgentConfigCreate,
)
from api.authentication.utils import _User, get_current_active_user
from api.chat.sql_stat.u2a_session.utils import (
    _U2ASessionCreate,
    get_latest_session_by_created_by,
    insert_session,
)
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    create_root_task_with_branch,
)
from api.chat.sql_stat.u2a_user_msg.utils import (
    get_user_messages_by_session_with_limit,
)

from api.sql_utils.utils import SQL_OP_ContextData

from .data_model import (
    CreateSessionRequest,
    CreateSessionResponse,
)
from .router_declare import router


def _build_default_scope_def(user_id: str) -> dict:
    """为新建会话构建默认 scope_def。"""
    return {
        "user_id_for_scope": user_id,
        "user_permission_role": "owner",
        "allowed_rel_dirs_in_juicefs_for_tool": [],
        "bash_tool": {
            "user_id_for_scope": user_id,
        },
        "file_ops_tool": {
            "user_id_for_scope": user_id,
            "user_permission_role": "owner",
            "white_list": [],
        },
        "skills_tool": {
            "user_id_for_scope": user_id,
            "user_permission_role": "owner",
            "search_paths": [],
        },
        "sub_agent_tool": {
            "user_id_for_scope": user_id,
            "user_permission_role": "owner",
            "search_paths": [],
        },
    }


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

        # 创建新会话 — 三步合并在一个事务内
        session_data = _U2ASessionCreate(
            user_id=current_user.id,
            title=request.title,
            created_by="user",
        )

        ctx = SQL_OP_ContextData(
            description="create_session: session + config + root_task_and_branch",
            auto_commit=False,
        )
        async with ctx:
            new_session_id = await insert_session(session_data, ctx=ctx)

            config = DEFAULT_MAIN_AGENT_SESSION_CONFIG.model_copy(deep=True)
            config.scope_def = _build_default_scope_def(str(current_user.id))
            await insert_session_config(
                _U2ASessionAgentConfigCreate(
                    session_id=new_session_id,
                    config=config.model_dump(mode="json"),
                ),
                ctx=ctx,
            )

            await create_root_task_with_branch(
                new_session_id,
                current_user.id,
                "main",
                "user",
                ctx=ctx,
            )

            await ctx.commit()

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
