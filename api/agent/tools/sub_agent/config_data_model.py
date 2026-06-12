# api/agent/tools/sub_agent/config_data_model.py

"""sub_agent 工具的配置和参数定义。"""

from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import BaseModel, Field

from api.agent.tools.config_data_model import SessionToolConfigBase, turn_pydantic_model_to_json_schema
from api.agent.tools.type import UserToolCallingPermissionRole

SUB_AGENT_USER_ID_PATHS: list[str] = ["sub_agent_tool.user_id_for_scope", "user_id_for_scope"]
SUB_AGENT_ROLE_PATHS: list[str] = ["sub_agent_tool.user_permission_role", "user_permission_role"]
SUB_AGENT_SEARCH_PATHS: list[str] = ["sub_agent_tool.search_paths", "allowed_rel_dirs_in_juicefs_for_tool"]


class SubAgentToolScope(BaseModel):
    """sub_agent 工具的作用域配置。"""
    user_id_for_scope: UUID
    role: UserToolCallingPermissionRole
    search_paths: list[PurePosixPath] = []


class SubAgentToolConfig(SessionToolConfigBase):
    enabled: bool = True
    explicit: bool = True
    tool_scope: SubAgentToolScope | None = None

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
