# api/agent/tools/skills/load_skill/constructor.py

"""load_skill 工具的构造器和实现。"""

from typing import Any
from uuid import UUID

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.agent.tools.skills.definition_loader import load_skill_definition
from api.agent.tools.skills.data_model import LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT, SkillDefinition, SkillLoadResult

from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    update_branch_storage_snapshot,
)

from .config_data_model import (
    LoadSkillConfig,
    LoadSkillParamDefine,
    LOAD_SKILL_GENERATION_TOOL_PARAM,
    TOOL_NAME,
)
from .utils import _format_skill_info

# 用于在 update_fn 闭包中传递 skill_name 和标记重复
_DuplicateMark = object()

class LoadSkillTool:
    """加载技能信息的工具。"""

    def __init__(self, config: LoadSkillConfig, user_id: UUID, session_id: UUID, branch_name: str):
        self.config = config
        self.user_id = user_id
        self.session_id = session_id
        self.branch_name = branch_name

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 参数验证
        try:
            param = LoadSkillParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True
            )

        # 加载技能定义
        skill_def = await load_skill_definition(self.user_id, param.name)

        if skill_def is None:
            return ToolTaskResult(
                str_content=f"未找到技能: {param.name}",
                occur_error=True
            )

        # 用于在闭包中标记是否重复
        result_holder: list[Any] = []

        def _update_loaded_skills(snapshot: dict[str, Any]) -> bool:
            loaded_skills: list[str] = snapshot.setdefault(LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT, [])
            if skill_def.name in loaded_skills:
                result_holder.append(_DuplicateMark)
                return False
            snapshot[LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT] = [*loaded_skills, skill_def.name]
            return True

        # 在锁保护下更新技能加载状态
        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=_update_loaded_skills,
        )

        if result_holder and result_holder[0] is _DuplicateMark:
            return ToolTaskResult(
                str_content=f" {skill_def.name} 技能已加载, 请勿重复调用",
                occur_error=True
            )

        # 格式化输出
        str_content = _format_skill_info(skill_def)

        json_content = SkillLoadResult(
            name=skill_def.name,
            description=skill_def.description,
            directory_path=skill_def.directory_path,
            directory_tree=skill_def.directory_tree,
            skill_md_content=skill_def.skill_md_content,
            available_resources={
                "template": skill_def.has_template,
                "examples": skill_def.has_examples,
                "scripts": skill_def.has_scripts,
            }
        ).model_dump()

        return ToolTaskResult(
            str_content=str_content,
            json_content=json_content,
            occur_error=False
        )

def construct_load_skill(
    config: LoadSkillConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 load_skill 工具实例。

    Args:
        config: 工具配置
        **kwargs: 注入参数（需要 user_id_for_scope, session_id, branch_name）

    Returns:
        (工具参数, 工具闭包) 元组

    Raises:
        ValueError: 缺少必需参数时
    """
    user_id: UUID | None = kwargs.get("user_id_for_scope")
    session_id: UUID | None = kwargs.get("session_id")
    branch_name: str | None = kwargs.get("branch_name")

    if user_id is None:
        raise ValueError("user_id_for_scope is required")
    if session_id is None:
        raise ValueError("session_id is required")
    if branch_name is None:
        raise ValueError("branch_name is required")

    tool = LoadSkillTool(config=config, user_id=user_id, session_id=session_id, branch_name=branch_name)

    return (LOAD_SKILL_GENERATION_TOOL_PARAM, tool)


CONSTRUCTOR = {TOOL_NAME: construct_load_skill}
