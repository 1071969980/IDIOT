# api/agent/tools/skills/unload_skill/constructor.py

"""unload_skill 工具的构造器和实现。"""

from typing import Any
from uuid import UUID

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.agent.tools.skills.data_model import LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT

from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    update_branch_storage_snapshot,
)

from .config_data_model import (
    UnloadSkillConfig,
    UnloadSkillParamDefine,
    UNLOAD_SKILL_GENERATION_TOOL_PARAM,
    TOOL_NAME,
)

_NotFoundMark = object()


class UnloadSkillTool:
    """卸载已加载技能的工具。"""

    def __init__(self, config: UnloadSkillConfig, user_id: UUID, session_id: UUID, branch_name: str):
        self.config = config
        self.user_id = user_id
        self.session_id = session_id
        self.branch_name = branch_name

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 参数验证
        try:
            param = UnloadSkillParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join(
                f"{'.'.join(str(l) for l in err['loc'])} - {err['msg']}"
                for err in e.errors()
            )
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True
            )

        # 用于在闭包中标记是否未找到
        result_holder: list[Any] = []

        def _update_loaded_skills(snapshot: dict[str, Any]) -> bool:
            loaded_skills: list[str] = snapshot.setdefault(LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT, [])
            if param.name not in loaded_skills:
                result_holder.append(_NotFoundMark)
                return False
            snapshot[LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT] = [s for s in loaded_skills if s != param.name]
            return True

        # 在锁保护下更新技能加载状态
        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=_update_loaded_skills,
        )

        if result_holder and result_holder[0] is _NotFoundMark:
            return ToolTaskResult(
                str_content=f"技能 {param.name} 未加载，无法卸载",
                occur_error=True
            )

        return ToolTaskResult(
            str_content=f"技能 {param.name} 已成功卸载",
            json_content={"unloaded_skill": param.name},
            occur_error=False
        )


def construct_unload_skill(
    config: UnloadSkillConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 unload_skill 工具实例。

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

    tool = UnloadSkillTool(config=config, user_id=user_id, session_id=session_id, branch_name=branch_name)

    return (UNLOAD_SKILL_GENERATION_TOOL_PARAM, tool)


CONSTRUCTOR = {TOOL_NAME: construct_unload_skill}
