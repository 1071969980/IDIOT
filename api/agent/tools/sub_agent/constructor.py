# api/agent/tools/sub_agent/constructor.py

"""sub_agent 工具构造器。"""

import logfire
from pathlib import PurePosixPath
from typing import Any
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import ValidationError
from uuid import UUID

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure, UserToolCallingPermissionRole
from api.agent.session_agent_config.utils import resolve_scope_value

from .agent_runner import SubAgentRunner
from .config_data_model import (
    SubAgentToolConfig,
    SubAgentToolScope,
    SubAgentParamDefine,
    TOOL_NAME,
    GENERATION_TOOL_PARAM,
    SUB_AGENT_USER_ID_PATHS,
    SUB_AGENT_ROLE_PATHS,
    SUB_AGENT_SEARCH_PATHS,
)
from .definition_loader import (
    SubAgentDefinition,
    load_user_agent_definitions,
)


class SubAgentTool:
    """sub_agent 工具主类。"""

    def __init__(
        self,
        config: SubAgentToolConfig,
        user_id: UUID,
        scope: SubAgentToolScope,
        session_id: UUID,
        session_task_id: UUID,
        branch_name: str,
        llm_service_name: str,
    ):
        self.config = config
        self.user_id = user_id
        self.scope = scope
        self.session_id = session_id
        self.session_task_id = session_task_id
        self._agent_definitions: dict[str, SubAgentDefinition] | None = None
        self.branch_name = branch_name
        self.llm_service_name = llm_service_name

    async def _ensure_definitions_loaded(self) -> dict[str, SubAgentDefinition]:
        """确保子代理定义已加载（延迟加载 + 缓存）。"""
        if self._agent_definitions is None:
            self._agent_definitions = await load_user_agent_definitions(
                self.scope.user_id_for_scope,
                role=self.scope.role,
                search_paths=self.scope.search_paths,
            )
        return self._agent_definitions

    async def __call__(self, **kwargs) -> ToolTaskResult:
        """工具调用入口。"""
        # 1. 参数验证
        try:
            param = SubAgentParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join(
                f"{'.'.join(str(l) for l in err['loc'])} - {err['msg']}"
                for err in e.errors()
            )
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True
            )

        # 2. 加载 agent 定义（首次调用时延迟加载并缓存）
        agent_definitions = await self._ensure_definitions_loaded()
        try:
            agent_definition = agent_definitions[param.agent_name]
        except KeyError:
            return ToolTaskResult(
                str_content=f"未找到指定的子代理：{param.agent_name}",
                occur_error=True
            )

        # 3. 解析有效参数（参数回退逻辑）
        effective_context_mode = param.context_mode or agent_definition.default_context_mode
        effective_should_feedback = (
            param.should_feedback if param.should_feedback is not None
            else agent_definition.default_should_feedback
        )

        cancel_event = kwargs.get("cancel_event", None)

        # 4. 创建并运行子代理
        try:
            runner = SubAgentRunner(
                agent_def=agent_definition,
                user_id=self.user_id,
                scope_user_id=self.scope.user_id_for_scope,
                session_id=self.session_id,
                branch_name=self.branch_name,
                session_task_id=self.session_task_id,
                llm_service_name=self.llm_service_name,
                cancel_event=cancel_event,
            )
            result = await runner.run(
                task=param.task,
                context_mode=effective_context_mode,
                should_feedback=effective_should_feedback,
            )
            return result  # runner.run() 已经返回 ToolTaskResult
        except Exception as e:
            logfire.error(f"sub_agent 工具执行异常: {e}")
            return ToolTaskResult(
                str_content=f"子代理执行时发生错误：{str(e)}。请不要以相同的方式重试。",
                occur_error=True
            )


async def construct_sub_agent_tool(
    config: SubAgentToolConfig,
    scope_def: dict[str, Any],
    **kwargs
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 sub_agent 工具。

    Args:
        config: 工具配置
        scope_def: 作用域定义字典
        **kwargs: 其他参数（user_id, session_id, session_task_id, branch_name, llm_service_name）

    Returns:
        (工具参数, 工具闭包) 元组

    Raises:
        ValueError: 缺少必需参数或配置无效时
    """
    user_id: UUID = kwargs.get("user_id") # type: ignore
    session_id: UUID = kwargs.get("session_id") # type: ignore
    session_task_id: UUID = kwargs.get("session_task_id") # type: ignore
    branch_name: str = kwargs.get("branch_name")  # type: ignore
    llm_service_name: str = kwargs.get("llm_service_name")  # type: ignore

    if user_id is None or session_id is None or session_task_id is None:
        raise ValueError("user_id, session_id, session_task_id are required")
    if branch_name is None:
        raise ValueError("branch_name is required")
    if llm_service_name is None:
        raise ValueError("llm_service_name is required")

    # 优先级 1: config 已有 tool_scope
    scope = config.tool_scope

    # 优先级 2: 从 scope_def 解析
    if scope is None:
        user_id_raw = resolve_scope_value(scope_def, SUB_AGENT_USER_ID_PATHS)
        scope_user_id = UUID(user_id_raw) if isinstance(user_id_raw, str) else user_id_raw
        role_raw = resolve_scope_value(scope_def, SUB_AGENT_ROLE_PATHS)
        role = UserToolCallingPermissionRole(role_raw) if isinstance(role_raw, str) else role_raw
        search_paths_raw = resolve_scope_value(scope_def, SUB_AGENT_SEARCH_PATHS) or []
        search_paths = [PurePosixPath(p) if isinstance(p, str) else p for p in search_paths_raw]

        scope = SubAgentToolScope(
            user_id_for_scope=scope_user_id,
            role=role,
            search_paths=search_paths,
        )

    # 将 scope 写入 config
    config = config.model_copy(update={"tool_scope": scope})

    tool = SubAgentTool(
        config=config,
        user_id=user_id,
        scope=scope,
        session_id=session_id,
        session_task_id=session_task_id,
        branch_name=branch_name,
        llm_service_name=llm_service_name,
    )

    return GENERATION_TOOL_PARAM, tool


# 构造器注册字典
CONSTRUCTOR = {TOOL_NAME: construct_sub_agent_tool}
