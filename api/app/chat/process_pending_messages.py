import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException

from api.agent.session_agent_config.config_data_model import (
    SessionAgentConfig,
)
from api.agent.session_agent_config.constants import (
    DEFAULT_MAIN_AGENT_SESSION_CONFIG,
)
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_keys import StorageSnapshotKeys
from api.agent.session_agent_config.utils import deep_update_dict
from api.agent.sql_stat.u2a_session_agent_config.utils import get_session_config_by_session_id, update_session_config
from api.app.graceful_shutdown import set_following_task_for_graceful_shutdown
from api.authentication.utils import _User, get_current_active_user
from api.chat.chat_task import session_chat_task
from api.chat.tool_init import init_tools
from api.chat.render_system_prompt import render_system_prompt
from api.load_balance.data_model import RetryConfigForAPIError
from api.chat.sql_stat.u2a_session.utils import (
    get_session,
)
from api.chat.sql_stat.u2a_session_branch.utils import (
    get_branch_by_session_and_name,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    copy_storage_snapshot_from_nearest_ancestor,
    get_ancestors_by_leaf_task_and_statuses,
    get_task,
    update_task_status,
    update_task_storage_snapshot,
)
from api.chat.sql_stat.u2a_user_msg.utils import (
    get_user_messages_by_session_task_id,
    update_user_message_status_by_ids,
)
from api.load_balance.constant import GLM_5_SERVICE_NAME, GLM_RETRY_CONFIG_FOR_APIERROR
from api.redis.distributed_lock import RedisDistributedLock
from api.redis.lock_names import LockNames
from api.sql_utils.utils import SQL_OP_ContextData

from .data_model import (
    ProcessPendingMessagesRequest,
    ProcessPendingMessagesResponse,
)
from .exception import (
    BranchNotFoundError,
    BranchProcessingConflictError,
    ChatProcessingError,
    NoPendingMessagesError,
    NoPendingTaskError,
    SessionConfigConsturctionError,
    SessionNotFoundError,
    SessionNotOwnedError,
    SystemPromptNotConfiguredError,
)
from .router_declare import router


@router.post("/process_pending_messages", response_model=ProcessPendingMessagesResponse)
async def process_pending_messages(
    request: ProcessPendingMessagesRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> ProcessPendingMessagesResponse:
    try:
        return await _process_pending_messages(current_user.id,
                                               request.session_id,
                                               request.branch_name,
                                               GLM_5_SERVICE_NAME,
                                               GLM_RETRY_CONFIG_FOR_APIERROR)
    except ChatProcessingError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail,
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"处理未回复消息时发生错误: {e!s}",
        ) from e

async def _process_pending_messages(
    user_id: UUID,
    session_id: UUID,
    branch_name: str,
    llm_service_name: str,
    retry_config: RetryConfigForAPIError | None = None,
) -> ProcessPendingMessagesResponse:
    """
    处理指定会话分支中还未被AI回复的消息。

    找到 branch 上 pending 状态的 task，收集绑定到该 task 的 waiting 消息，
    更新状态并启动 AI 处理。

    Args:
        request: 包含会话ID和分支名称的请求对象
        current_user: 当前认证用户

    Returns:
        ProcessPendingMessagesResponse: 包含已处理消息列表的响应对象
    """
    async with RedisDistributedLock(
        key=LockNames.process_pending_messages_pre_process(session_id, branch_name)
    ):
        # 1. 会话存在性验证和所有权验证
        session = await get_session(session_id)
        if session is None:
            raise SessionNotFoundError("会话不存在")
        if session.user_id != user_id:
            raise SessionNotOwnedError("会话不属于当前用户")

        # 2. 查找分支
        branch = await get_branch_by_session_and_name(
            session_id, branch_name
        )
        if branch is None:
            raise BranchNotFoundError("该分支不存在或没有待处理的消息")

        # 3. 获取 leaf task 并验证状态
        leaf_task = await get_task(branch.leaf_task_id)
        if leaf_task is None or leaf_task.status != "pending":
            raise NoPendingTaskError("分支或已处理完毕")

        # 4. 收集绑定到该 task 的等待消息
        all_task_messages = await get_user_messages_by_session_task_id(leaf_task.id)
        pending_messages = [
            msg for msg in all_task_messages
            if msg.status == "waiting_agent_ack_user"
        ]

        if not pending_messages:
            raise NoPendingMessagesError("没有待处理的消息")

        # 5. 检查该分支路径上是否有正在处理的任务
        branch_processing_tasks = await get_ancestors_by_leaf_task_and_statuses(
            leaf_task.id, ["processing"]
        )

        if branch_processing_tasks:
            raise BranchProcessingConflictError("当前分支有正在处理的任务")
        
        try: 
            # 6. 构造 session_config
            # 获得会话agent配置
            session_config_row = await get_session_config_by_session_id(session_id)
            if not session_config_row:
                raise ValueError("会话配置不存在")
            session_config = SessionAgentConfig.model_validate(session_config_row.config)
            if session_config.version.major != DEFAULT_MAIN_AGENT_SESSION_CONFIG.version.major:
                raise ValueError("会话配置版本不兼容")

            # 7. 检查 storage_snapshot，若不存在则从最近祖先复制，无祖先则新建空快照
            task_uuid = leaf_task.id
            if leaf_task.storage_snapshot is None:
                raise ValueError("task storage_snapshot 不存在")
            task_storage_snapshot = leaf_task.storage_snapshot

            # 8. 构造 session_config 的覆盖层
            if task_storage_snapshot is not None and StorageSnapshotKeys.SESSION_CONFIG_OVERLAY in task_storage_snapshot:
                session_config_overlay = task_storage_snapshot.get(StorageSnapshotKeys.SESSION_CONFIG_OVERLAY, {})
                if not isinstance(session_config_overlay, dict):
                    raise SessionConfigConsturctionError(f"{StorageSnapshotKeys.SESSION_CONFIG_OVERLAY} 类型错误")
                session_config_base = session_config.model_dump(mode="json")
                session_config_final = deep_update_dict(session_config_base, session_config_overlay)
                session_config = SessionAgentConfig.model_validate(session_config_final)


        except Exception as e:
            raise SessionConfigConsturctionError(f"session_config 构建时发生错误: {e!s}") from e

        # 9. 构造系统提示
        system_prompt = render_system_prompt(session_config.system_prompt_config)
        if not system_prompt:
            raise SystemPromptNotConfiguredError("系统提示未配置")

        # 10-11. 原子更新 task 和消息状态（同一事务）
        ctx = SQL_OP_ContextData(description="process_pending_messages: task+msg status transition")
        try:
            await update_task_status(task_uuid, "processing", ctx=ctx)
            await update_user_message_status_by_ids(
                [msg.id for msg in pending_messages],
                "agent_working_for_user",
                ctx=ctx,
            )
            await ctx.commit()
        except Exception:
            await ctx.rollback()
            raise

    # 12. 初始化工具并创建后台任务，失败时回滚状态
    try:
        scope_def = session_config.scope_def
        tool_init_res, mcp_tools_loader = await init_tools(
            user_id=user_id,
            session_id=session.id,
            session_task_id=task_uuid,
            branch_name=branch_name,
            llm_service_name=llm_service_name,
            session_config=session_config,
            scope_def=scope_def,
        )

        # 发起后台任务
        with set_following_task_for_graceful_shutdown():
            asyncio.create_task(session_chat_task( # type: ignore # noqa: RUF006
                user_id=user_id,
                session_id=session.id,
                session_task_id=task_uuid,
                branch_name=branch_name,
                llm_service_name=llm_service_name,
                system_prompt=system_prompt,
                pending_messages=pending_messages,
                during_processing_tasks=branch_processing_tasks,
                tool_init_res=tool_init_res,
                mcp_tools_loader=mcp_tools_loader,
                scope_def=scope_def,
                retry_config=retry_config,
            ))

        return ProcessPendingMessagesResponse(
            session_id=session.id,
            session_task_id=task_uuid,
            processed_messages_id_status_map={msg.id: "agent_working_for_user" for msg in pending_messages},
            total_processed=len(pending_messages)
        )
    except Exception:
        # 尚未成功创建 session_chat_task 或返回响应前异常，回滚 task 和消息状态
        try:
            await update_task_status(task_uuid, "pending")
            await update_user_message_status_by_ids(
                [msg.id for msg in pending_messages],
                "waiting_agent_ack_user",
            )
        except Exception:
            pass
        raise
