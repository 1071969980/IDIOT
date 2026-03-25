# api/agent/tools/skills/skill_advisor/config_data_model.py

"""skill_advisor 工具的配置和参数定义。"""

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import SessionToolConfigBase, turn_pydantic_model_to_json_schema

TOOL_NAME = "skill_advisor"


class SkillAdvisorConfig(SessionToolConfigBase):
    """skill_advisor 工具配置。"""

    enabled: bool = True


class SkillAdvisorParamDefine(BaseModel):
    """skill_advisor 工具的参数定义。"""

    prompt: str = Field(
        ...,
        description="描述接下来要处理的问题，用于匹配相关技能"
    )

    model_config = ConfigDict(extra='allow')


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: SkillAdvisorConfig(enabled=True)
}


SKILL_ADVISOR_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "根据任务描述，返回可能相关的技能列表。"
            "当你需要发现哪些技能可能有助于完成任务时使用此工具。"
        ),
        parameters=turn_pydantic_model_to_json_schema(SkillAdvisorParamDefine),
    )
)