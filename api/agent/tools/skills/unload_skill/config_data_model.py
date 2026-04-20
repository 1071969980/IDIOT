# api/agent/tools/skills/unload_skill/config_data_model.py

"""unload_skill 工具的配置和参数定义。"""

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import SessionToolConfigBase, turn_pydantic_model_to_json_schema

TOOL_NAME = "unload_skill"


class UnloadSkillConfig(SessionToolConfigBase):
    """unload_skill 工具配置。"""
    enabled: bool = True
    explicit: bool = True


class UnloadSkillParamDefine(BaseModel):
    """unload_skill 工具的参数定义。"""

    name: str = Field(
        ...,
        description="要卸载的技能名称"
    )

    model_config = ConfigDict(extra='allow')


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: UnloadSkillConfig(
        enabled=True,
        explicit=True
        )
}


UNLOAD_SKILL_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "卸载已加载的技能，将其从当前会话的已加载技能列表中移除。"
            "当你不再需要某个技能时使用此工具。"
        ),
        parameters=turn_pydantic_model_to_json_schema(UnloadSkillParamDefine),
    )
)
