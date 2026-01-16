"""ask_user_offline_cli 工具的配置和参数定义"""

from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import (
    SessionToolConfigBase,
    turn_pydantic_model_to_json_schema,
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

TOOL_NAME = "ask_user"


class AskUserOfflineCliConfig(SessionToolConfigBase):
    """AskUserOfflineCli 工具的配置类

    Attributes:
        enabled: 是否启用工具
    """

    enabled: bool = True


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: AskUserOfflineCliConfig(enabled=True)
}


class AskUserOfflineCliToolParamDefine(BaseModel):
    """AskUserOfflineCli 工具的参数定义

    用于在命令行环境中向用户提问并获取选择
    """

    question: str = Field(description="The question you want to ask the user")
    options: list[str] = Field(
        description="Options for user to choose from. "
    )
    allow_additional_input: bool = Field(
        default=True,
        description=(
            "Whether to allow user to express their own choice that you did not "
        ),
    )

    model_config = ConfigDict(extra="allow")


GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "Ask user to choose from a list of options, and optionally allow them to express their own choice that you did not provide in the options."
        ),
        parameters=turn_pydantic_model_to_json_schema(
            AskUserOfflineCliToolParamDefine
        ),
        parameters_example={
            "question": "What is your favorite color?",
            "options": ["red", "blue", "green"],
            "allow_additional_input": True,
        },
    ),  # type: ignore
)
