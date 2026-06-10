# api/agent/tools/skills/load_skill/config_data_model.py

"""load_skill 工具的配置和参数定义。"""

from pathlib import PurePosixPath
from uuid import UUID

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import SessionToolConfigBase, turn_pydantic_model_to_json_schema
from api.agent.tools.type import UserToolCallingPermissionRole

TOOL_NAME = "load_skill"

# scope 解析键，按优先级排列。点号分隔表示嵌套路径。
# 工具特定路径优先，回退到通用路径。
LOAD_SKILL_USER_ID_PATHS: list[str] = ["skills_tool.user_id_for_scope", "user_id_for_scope"]
LOAD_SKILL_ROLE_PATHS: list[str] = ["skills_tool.user_permission_role", "user_permission_role"]
LOAD_SKILL_PROJ_PATHS: list[str] = ["skills_tool.allowed_rel_dirs_in_juicefs_for_tool", "allowed_rel_dirs_in_juicefs_for_tool"]


class SkillConflictError(Exception):
    """技能在多个搜索路径中同名冲突。"""


class SkillToolScope(BaseModel):
    """load_skill 工具的作用域配置。"""
    user_id_for_scope: UUID
    role: UserToolCallingPermissionRole
    proj_paths: list[PurePosixPath] = []


class LoadSkillConfig(SessionToolConfigBase):
    """load_skill 工具配置。"""
    enabled: bool = True
    explicit: bool = True
    tool_scope: SkillToolScope | None = None


class LoadSkillParamDefine(BaseModel):
    """load_skill 工具的参数定义。"""

    name: str = Field(
        ...,
        description="要加载的技能名称（目录名或显示名）"
    )

    model_config = ConfigDict(extra='allow')


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: LoadSkillConfig(
        enabled=True,
        explicit=True
        )
}


LOAD_SKILL_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "加载技能的完整信息，包括名称、描述、目录结构和 SKILL.md 内容。"
            "当你需要理解或应用特定技能时使用此工具。"
        ),
        parameters=turn_pydantic_model_to_json_schema(LoadSkillParamDefine),
    )
)