# api/agent/tools/feed_message/config_data_model.py

"""feed_message 工具的配置和参数定义。"""

from typing import Union

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.agent.tools.config_data_model import SessionToolConfigBase, turn_pydantic_model_to_json_schema

TOOL_NAME = "feed_message"


class FeedMessageConfig(SessionToolConfigBase):
    """feed_message 工具配置。"""
    enabled: bool = True
    explicit: bool = True


class FeedMessageParamDefine(BaseModel):
    """feed_message 工具的参数定义。"""

    branch_name: str | None = Field(
        default=None,
        description="目标分支名称，消息将发送到该分支，并要求其进行处理。与 sub_agent_alias 二选一。"
    )
    sub_agent_alias: str | None = Field(
        default=None,
        description="子代理别名，用于代替 branch_name 指定目标分支。与 branch_name 二选一。"
    )
    message: Union[str, list[str]] = Field(
        ...,
        description="要发送的消息内容，支持单条字符串或多条消息列表"
    )
    trigger_processing: bool = Field(
        default=True,
        description="发送消息后是否触发目标分支立即处理。默认 True。设为 False 时消息仅投递入队列，不会立即处理。"
    )

    model_config = ConfigDict(extra='allow')

    @model_validator(mode='after')
    def check_branch_or_alias(self) -> 'FeedMessageParamDefine':
        if self.branch_name is None and self.sub_agent_alias is None:
            raise ValueError('必须提供 branch_name 或 sub_agent_alias 之一')
        if self.branch_name is not None and self.sub_agent_alias is not None:
            raise ValueError('branch_name 和 sub_agent_alias 不能同时提供，请只使用其中一个')
        return self


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
            "向当前会话指定分支发送消息。"
            "可以通过 branch_name 指定目标分支，或通过 sub_agent_alias 指定子代理别名。"
            "默认发送后会触发目标分支处理（trigger_processing=True），可设为 False 仅投递不触发。"
        ),
        parameters=turn_pydantic_model_to_json_schema(FeedMessageParamDefine),
    )
)
