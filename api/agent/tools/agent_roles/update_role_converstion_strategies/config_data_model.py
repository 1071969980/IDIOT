from __future__ import annotations

from uuid import UUID
from typing import Any, Coroutine, Literal

from pydantic import BaseModel, Field, ConfigDict
from openai.types.chat import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from api.agent.tools.config_data_model import SessionToolConfigBase
from api.agent.tools.type import ToolClosure
from api.agent.tools.config_data_model import turn_pydantic_model_to_json_schema

# 工具名称常量
TOOL_NAME = "update_conversation_strategies_of_role"


# 配置类
class UpdateConversationStrategiesOfRoleToolConfig(SessionToolConfigBase):
    pass  # 目前没有特定配置项，仅使用基类的 enabled 字段


# 默认配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: UpdateConversationStrategiesOfRoleToolConfig(enabled=True)
}

AvailableRole = Literal["User-Delegated Agent"]

# 参数定义类
class UpdateConversationStrategiesOfRoleToolParamDefine(BaseModel):
    role_name:AvailableRole = Field(description="role name")
    update_content: str = Field(description="update content")
    context: str = Field(description="context")

    model_config = ConfigDict(extra='allow')

tool_description = """
This tool is used to request updates to the conversational strategies of other AI agent roles.\
 The role name, the content to be updated, and relevant contextual information should be provided.\
 Submitted text will not be directly adopted but will be processed by separate workflows that cannot access the current context.\
 Therefore, submitted text must be fully self-contained.\
 The tool's output only indicates whether the update task was successfully submitted and does not reflect the actual update results.
The update content parameter should be phrased as imperative sentences.\
 Avoid using first or second person pronouns whenever possible.\
 Unless otherwise specified by the user, refer to potential interlocutors of other AI agent roles as “the others.”\
 If the user mentions themselves, use “the user” to refer to them.
 For example, if a user says: “When someone try to contact me, politely decline on my behalf.But if it's Dennis, make a note and let me know later.”\
 The update should be phrased as: “When others ask if the user is available, politely decline their request. If Dennis comes looking for the user, make a note of it and inform the user later, while also responding politely to Dennis.”
The context parameter must provide all necessary explanations and a summary of the current conversation history (relevant to the update content) to assist other processing workflows in correctly understanding and performing incremental updates to the role's dialogue script.\
 In the example above, an appropriate context could be information about Dennis mentioned in the dialogue or within other memory tools, enabling other AI agent roles to more accurately identify each interlocutor`s identities and execute conversation strategies.
"""

# OpenAI 工具参数
GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=tool_description,
        parameters=turn_pydantic_model_to_json_schema(UpdateConversationStrategiesOfRoleToolParamDefine)
    )
)