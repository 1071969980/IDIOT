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

from api.chat.sql_stat.u2a_session_task.utils import get_task, update_task_storage_snapshot
from api.redis.distributed_lock import RedisDistributedLock
from api.redis.lock_names import LockNames

from .config_data_model import (
    LoadSkillConfig,
    LoadSkillParamDefine,
    LOAD_SKILL_GENERATION_TOOL_PARAM,
    TOOL_NAME,
)


class LoadSkillTool:
    """加载技能信息的工具。"""

    def __init__(self, config: LoadSkillConfig, user_id: UUID, session_task_id: UUID):
        self.config = config
        self.user_id = user_id
        self.session_task_id = session_task_id

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

        # 更新技能加载状态到任务存储快照
        lock_key = LockNames.task_storage_snapshot(self.session_task_id)
        async with RedisDistributedLock(lock_key):
            task = await get_task(self.session_task_id)
            if task is None:
                raise ValueError("session task is None")
            if task.storage_snapshot is None:
                raise ValueError("session task storage_snapshot is None")
            loaded_skills: list[str] = task.storage_snapshot.setdefault(LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT, [])
            if skill_def.name in loaded_skills:
                return ToolTaskResult(
                    str_content=f" {skill_def.name} 技能已加载, 请勿重复调用",
                    occur_error=True
                )

            task.storage_snapshot[LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT] = [*loaded_skills, skill_def.name]
            await update_task_storage_snapshot(
                self.session_task_id,
                task.storage_snapshot
            )

        # 格式化输出
        str_content = self._format_skill_info(skill_def)

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

    def _format_skill_info(self, skill_def: SkillDefinition) -> str:
        """格式化技能信息为可读文本。"""
        lines = [
            f"# 技能: {skill_def.name}",
            f"\n**描述:** {skill_def.description}",
            f"\n**路径:** {skill_def.directory_path}",
            f"\n## 目录结构",
            "```",
            skill_def.directory_tree,
            "```",
            f"\n## SKILL.md 内容",
            "```markdown",
            skill_def.skill_md_content,
            "```",
        ]

        resources = []
        if skill_def.has_template:
            resources.append("template.md")
        if skill_def.has_examples:
            resources.append("examples/")
        if skill_def.has_scripts:
            resources.append("scripts/")

        if resources:
            lines.append(f"\n**可用资源:** {', '.join(resources)}")

        return "\n".join(lines)


def construct_load_skill(
    config: LoadSkillConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 load_skill 工具实例。

    Args:
        config: 工具配置
        **kwargs: 注入参数（需要 user_id_for_scope）

    Returns:
        (工具参数, 工具闭包) 元组

    Raises:
        ValueError: 缺少必需参数时
    """
    user_id: UUID | None = kwargs.get("user_id_for_scope")
    session_task_id:  UUID | None = kwargs.get("session_task_id")

    if user_id is None:
        raise ValueError("user_id_for_scope is required")
    if session_task_id is None:
        raise ValueError("session_task_id is required")

    tool = LoadSkillTool(config=config, user_id=user_id, session_task_id=session_task_id)

    return (LOAD_SKILL_GENERATION_TOOL_PARAM, tool)


CONSTRUCTOR = {TOOL_NAME: construct_load_skill}