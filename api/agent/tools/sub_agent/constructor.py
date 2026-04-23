# api/agent/tools/sub_agent/constructor.py

"""sub_agent 工具构造器。"""

import logfire
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import ValidationError
from uuid import UUID

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure

from .agent_runner import SubAgentRunner
from .config_data_model import SubAgentToolConfig, SubAgentParamDefine, TOOL_NAME, GENERATION_TOOL_PARAM
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
        session_id: UUID,
        session_task_id: UUID,
        branch_name: str,
        llm_service_name: str,
    ):
        """初始化 sub_agent 工具。

        Args:
            config: 工具配置
            user_id: 用户 ID
            session_id: 主 agent 的会话 ID
            session_task_id: 主 agent 的任务 ID
            branch_name: 当前分支名称
            llm_service_name: 当前使用的 LLM 服务名称
        """
        self.config = config
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self._agent_definitions: dict[str, SubAgentDefinition] | None = None
        self.branch_name = branch_name
        self.llm_service_name = llm_service_name

    async def _ensure_definitions_loaded(self) -> dict[str, SubAgentDefinition]:
        """确保子代理定义已加载（延迟加载 + 缓存）。"""
        if self._agent_definitions is None:
            self._agent_definitions = await load_user_agent_definitions(self.user_id)
        return self._agent_definitions

    async def __call__(self, **kwargs) -> ToolTaskResult:
        """工具调用入口。

        Args:
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        # 1. 参数验证
        try:
            param = SubAgentParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}",
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
    **kwargs
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 sub_agent 工具。

    创建工具实例并注入必要参数。
    子代理定义在首次调用时延迟加载，避免未使用时的 I/O 开销。

    Args:
        config: 工具配置
        **kwargs: 其他参数（user_id, session_id, session_task_id, branch_name, llm_service_name）

    Returns:
        (工具参数, 工具闭包) 元组
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

    tool = SubAgentTool(
        config=config,
        user_id=user_id,
        session_id=session_id,
        session_task_id=session_task_id,
        branch_name=branch_name,
        llm_service_name=llm_service_name,
    )

    return GENERATION_TOOL_PARAM, tool


# 构造器注册字典
CONSTRUCTOR = {TOOL_NAME: construct_sub_agent_tool}
