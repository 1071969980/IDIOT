from api.agent.tools.config_data_model import SessionToolConfigBase
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from pydantic import BaseModel, ConfigDict, Field

TOOL_NAME = "ask_user_choice"

class AskUserChoiceConfig(SessionToolConfigBase):
    pass

DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: AskUserChoiceConfig(enabled=True)
}

class AskUserChoiceToolParamDefine(BaseModel):
    question: str = Field(
        description="The question you want to ask the user"
    )
    options: list[str] = Field(
        description="Options for user to choose from"
    )
    allow_additional_input: bool = Field(
        default=True,
        description="Whether to allow user to express their own choice taht you did not provide in the options"
    )

    model_config = ConfigDict(extra='allow')

GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="Ask user to choose from a list of options, and optionally allow them to express their own choice that you did not provide in the options.",
        parameters=AskUserChoiceToolParamDefine.model_json_schema()
    )
)