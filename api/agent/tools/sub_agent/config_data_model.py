# api/agent/tools/sub_agent/config_data_model.py

"""sub_agent 工具的配置和参数定义。"""

from typing import Literal

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import BaseModel, Field

from api.agent.tools.config_data_model import SessionToolConfigBase, turn_pydantic_model_to_json_schema


class SubAgentToolConfig(SessionToolConfigBase):
    enabled: bool = True
    explicit: bool = True

class SubAgentParamDefine(BaseModel):
    """sub_agent 工具的参数定义。"""

    agent_name: str = Field(
        ...,
        description="要执行的子代理名称"
    )
    task: str = Field(
        ...,
        description="给子代理的任务描述文本"
    )
    context_mode: Literal["standalone", "fork"] | None = Field(
        None,
        description='上下文模式，"standalone"（独立上下文）或 "fork"（继承当前上下文），为空时使用子代理定义的默认值'
    )
    should_feedback: bool | None = Field(
        None,
        description="是否要求子代理使用 feed_message 工具向你反馈，为空时使用子代理定义文件中指定的默认值"
    )


# 工具名称常量
TOOL_NAME = "sub_agent"

# 默认配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: SubAgentToolConfig(enabled=True,
                                  explicit=True)
}

# 工具生成参数（用于 LLM Function Calling）
GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "创建一个子代理来执行任务。\n\n"
            "参数说明：\n"
            "- agent_name: 要执行的子代理名称\n"
            "- task: 给子代理的任务描述文本\n"
            "- context_mode: 上下文模式，\"standalone\"（独立上下文）或 \"fork\"（继承当前上下文），为空时使用子代理定义文件中指定的默认值\n"
            "- should_feedback: 是否要求子代理使用 feed_message 工具向你反馈，为空时使用子代理定义文件中指定的默认值"
        ),
        parameters=turn_pydantic_model_to_json_schema(SubAgentParamDefine),
    )  # type: ignore
)
