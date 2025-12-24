from typing import Any

from pydantic import BaseModel, Field, ConfigDict
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from api.agent.tools.config_data_model import SessionToolConfigBase

TOOL_NAME = "list_available_agent_roles"


class ListAvailableAgentRolesConfig(SessionToolConfigBase):
    """列出可用Agent角色工具的配置"""
    pass


class ListAvailableAgentRolesParamDefine(BaseModel):
    """列出可用Agent角色工具的参数定义（无参数）"""

    model_config = ConfigDict(extra='allow')


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: ListAvailableAgentRolesConfig(enabled=True)
}


GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="list available roles in this Multi-Role Agent System"
    )
)