# api/agent/tools/sub_agent/constructor.py

"""sub_agent 工具构造器。"""

import logfire
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import ValidationError
from uuid import UUID

from api.agent.tools.config_data_model import turn_pydantic_model_to_json_schema
from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure

from .agent_runner import SubAgentRunner
from .config_data_model import SubAgentToolConfig, SubAgentParamDefine, TOOL_NAME
from .definition_loader import SubAgentDefinition, load_all_agent_definitions
from .utils import format_tool_description


class SubAgentTool:
    """sub_agent 工具主类。"""

    def __init__(
        self,
        config: SubAgentToolConfig,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        agent_definitions: dict[str, SubAgentDefinition],
    ):
        """初始化 sub_agent 工具。

        Args:
            config: 工具配置
            user_id: 用户 ID
            session_id: 主 agent 的会话 ID
            session_task_id: 主 agent 的任务 ID
        """
        self.config = config
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self.agent_definitions = agent_definitions

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

        # 2. 加载 agent 定义
        try:
            agent_definition = self.agent_definitions[param.agent_name]
        except KeyError:
            return ToolTaskResult(
                str_content=f"未找到指定的子 agent：{param.agent_name}",
                occur_error=True
            )

        cancel_event = kwargs.get("cancel_event", None)

        # 3. 创建并运行子 agent
        try:
            runner = SubAgentRunner(
                user_id=self.user_id,
                parent_session_id=self.session_id,
                agent_definition=agent_definition,
                task=param.task,
                session_alias=param.session_alias,
                cancel_event=cancel_event,
            )
            result = await runner.run()

            return ToolTaskResult(str_content=result)
        except Exception as e:
            logfire.error(f"sub_agent 工具执行异常: {e}")
            return ToolTaskResult(
                str_content=f"子 agent 执行时发生错误：{str(e)}。请不要以相同的方式重试。",
                occur_error=True
            )


async def construct_sub_agent_tool(
    config: SubAgentToolConfig,
    **kwargs
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 sub_agent 工具。

    在工具构造时：
    1. 加载所有可用的子 agent 定义
    2. 生成包含可用 agent 列表的工具描述
    3. 创建工具实例并注入必要参数

    Args:
        config: 工具配置
        **kwargs: 其他参数（user_id, session_id, session_task_id）

    Returns:
        (工具参数, 工具闭包) 元组
    """
    user_id: UUID = kwargs.get("user_id") # type: ignore
    session_id: UUID = kwargs.get("session_id") # type: ignore
    session_task_id: UUID = kwargs.get("session_task_id") # type: ignore
    
    if user_id is None or session_id is None or session_task_id is None:
        raise ValueError("user_id, session_id, session_task_id are required")

    # 加载所有可用定义（用于生成描述）
    definitions = await load_all_agent_definitions(user_id)
    tool_description = format_tool_description(definitions)

    tool = SubAgentTool(
        config=config,
        user_id=user_id,
        session_id=session_id,
        session_task_id=session_task_id,
        agent_definitions=definitions
    )

    tool_param = ChatCompletionToolParam(
        type="function",
        function=FunctionDefinition(
            name=TOOL_NAME,
            description=tool_description,
            parameters=turn_pydantic_model_to_json_schema(SubAgentParamDefine)
        )
    )

    return tool_param, tool


# 构造器注册字典
CONSTRUCTOR = {TOOL_NAME: construct_sub_agent_tool}
