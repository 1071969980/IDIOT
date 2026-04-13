import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException

from api.agent.session_agent_config.config_data_model import (
    SessionAgentConfig,
)
from api.agent.session_agent_config.constants import (
    DEFAULT_MAIN_AGENT_SESSION_CONFIG,
    SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT,
)
from api.agent.sql_stat.u2a_session_agent_config.utils import get_session_config_by_session_id, update_session_config
from api.agent.tools.tool_factory import UserToolCallingPermissionRole
from api.app.graceful_shutdown import set_following_task_for_graceful_shutdown
from api.authentication.utils import _User, get_current_active_user
from api.chat.chat_task import init_tools, session_chat_task
from api.chat.render_system_prompt import render_system_prompt
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
from api.load_balance.constant import GLM_5_SERVICE_NAME
from api.redis.distributed_lock import RedisDistributedLock
from api.redis.lock_names import LockNames

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
        return await _process_pending_messages(request, current_user.id)
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

def deep_update_dict(original: dict, update_with: dict) -> dict:
    """
    递归地将 update_with 中的内容合并到 original 字典中。
    对于嵌套的字典会进行深度合并，其余类型直接覆盖。
    
    注意：该函数会就地修改 original 字典，并返回它。
    """
    for key, value in update_with.items():
        if isinstance(value, dict) and isinstance(original.get(key), dict):
            # 如果两边都是字典，则递归合并
            deep_update_dict(original[key], value)
        else:
            # 否则直接覆盖或新增
            original[key] = value
    return original

async def _process_pending_messages(
    request: ProcessPendingMessagesRequest,
    user_id: UUID,
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
        key=LockNames.process_pending_messages_pre_process(request.session_id, request.branch_name)
    ):
        # 1. 会话存在性验证和所有权验证
        session = await get_session(request.session_id)
        if session is None:
            raise SessionNotFoundError("会话不存在")
        if session.user_id != user_id:
            raise SessionNotOwnedError("会话不属于当前用户")

        # 2. 查找分支
        branch = await get_branch_by_session_and_name(
            request.session_id, request.branch_name
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
            session_config_row = await get_session_config_by_session_id(request.session_id)
            if session_config_row is None:
                # 初始化配置
                session_config = DEFAULT_MAIN_AGENT_SESSION_CONFIG
                await update_session_config(request.session_id, session_config.model_dump(mode="json"))
            else:
                session_config = SessionAgentConfig.model_validate(session_config_row.config)


            # 7. 检查 storage_snapshot，若不存在则从最近祖先复制，无祖先则新建空快照
            task_uuid = leaf_task.id
            task_storage_snapshot = None
            if leaf_task.storage_snapshot is None:
                copied = await copy_storage_snapshot_from_nearest_ancestor(task_uuid)
                if not copied:
                    await update_task_storage_snapshot(task_uuid, {})
                    task_storage_snapshot = {}
                else:
                    refetch_leaftask = await get_task(task_uuid)
                    task_storage_snapshot = refetch_leaftask.storage_snapshot if refetch_leaftask else None
            else:
                task_storage_snapshot = leaf_task.storage_snapshot

            # 8. 构造 session_config 的覆盖层
            if task_storage_snapshot is not None and SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT in task_storage_snapshot:
                session_config_overlay = task_storage_snapshot.get(SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT, {})
                if not isinstance(session_config_overlay, dict):
                    raise SessionConfigConsturctionError(f"{SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT} 类型错误")
                session_config_base = session_config.model_dump(mode="json")
                session_config_final = deep_update_dict(session_config_base, session_config_overlay)
                session_config = SessionAgentConfig.model_validate(session_config_final)

        except Exception as e:
            raise SessionConfigConsturctionError(f"session_config 构建时发生错误: {e!s}") from e

        # 9. 构造系统提示
        system_prompt = render_system_prompt(session_config.system_prompt_config)
        if not system_prompt:
            raise SystemPromptNotConfiguredError("系统提示未配置")

        # 10. 更新 task 状态为 processing
        await update_task_status(task_uuid, "processing")

        # 11. 更新消息状态为 agent_working_for_user
        await update_user_message_status_by_ids(
            [msg.id for msg in pending_messages],
            "agent_working_for_user",
        )

    # 12. 初始化工具并创建后台任务，失败时回滚状态
    try:
        tools, tool_call_function = await init_tools(
            user_id_for_scope=user_id,
            session_id=session.id,
            session_task_id=task_uuid,
            session_config=session_config,
            user_permission_role=UserToolCallingPermissionRole.OWNER,
            work_dirs=session_config.work_dirs,
        )

        # 13. 获取 MCP 配置
        if session_config.mcp_config and len(session_config.mcp_config.servers) > 0:
            mcp_config = session_config.mcp_config

        # 发起后台任务
        with set_following_task_for_graceful_shutdown():
            asyncio.create_task(session_chat_task( # type: ignore # noqa: RUF006
                user_id=user_id,
                session_id=session.id,
                session_task_id=task_uuid,
                llm_service=GLM_5_SERVICE_NAME,
                system_prompt=system_prompt,
                pending_messages=pending_messages,
                during_processing_tasks=branch_processing_tasks,
                tools=tools,
                tool_call_function=tool_call_function,
                mcp_config=mcp_config,
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
