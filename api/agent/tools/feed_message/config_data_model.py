# api/agent/tools/feed_message/config_data_model.py

"""feed_message 工具的配置和参数定义。"""

from typing import Union

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import SessionToolConfigBase, turn_pydantic_model_to_json_schema

TOOL_NAME = "feed_message"


class FeedMessageConfig(SessionToolConfigBase):
    """feed_message 工具配置。"""
    enabled: bool = True
    explicit: bool = True


class FeedMessageParamDefine(BaseModel):
    """feed_message 工具的参数定义。"""

    branch_name: str = Field(
        ...,
        description="目标分支名称，消息将发送到该分支，并要求其进行处理"
    )
    message: Union[str, list[str]] = Field(
        ...,
        description="要发送的消息内容，支持单条字符串或多条消息列表"
    )

    model_config = ConfigDict(extra='allow')


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: FeedMessageConfig(
        enabled=True,
        explicit=True,
    )
}


GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "向当前会话指定分支发送消息，并要求其进行处理。"
        ),
        parameters=turn_pydantic_model_to_json_schema(FeedMessageParamDefine),
    )
)
