from api.agent.tools.config_data_model import SessionToolConfigBase
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from pydantic import BaseModel, ConfigDict, Field

TOOL_NAME = "communication_task"

class CreateCommunicationTaskConfig(SessionToolConfigBase):
    pass

DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: CreateCommunicationTaskConfig(enabled=True)
}

class CreateCommunicationTaskToolParamDefine(BaseModel):
    target_user: str = Field(
        description="The user uuid or name that you want to communicate with",
    )
    session_id: str | None = Field(
        default=None,
        description="The session uuid that you want to resume",
    )
    goal: str = Field(
        description="the goal description you should follow and try to achieve in the communication task",
    )

    model_config = ConfigDict(extra='allow')

GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="Create a communication task to another user's acting agent",
        parameters=CreateCommunicationTaskToolParamDefine.model_json_schema()
    )
)