# api/agent/tools/skills/skill_advisor/constructor.py

"""skill_advisor 工具的构造器和实现。"""

import asyncio
from typing import Any
from uuid import UUID

import logfire
from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.agent.tools.skills.definition_loader import load_all_skill_infos

from .config_data_model import (
    SkillAdvisorConfig,
    SkillAdvisorParamDefine,
    SKILL_ADVISOR_GENERATION_TOOL_PARAM,
    TOOL_NAME,
)
from .advisor_runner import SkillAdvisorRunner


class SkillAdvisorTool:
    """根据任务描述推荐相关技能的工具。"""

    def __init__(
        self,
        config: SkillAdvisorConfig,
        user_id: UUID,
        session_id: UUID,
        cancel_event: asyncio.Event | None = None,
    ):
        self.config = config
        self.user_id = user_id
        self.session_id = session_id
        self.cancel_event = cancel_event

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 参数验证
        try:
            param = SkillAdvisorParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True
            )

        # 加载所有技能信息
        skill_infos = await load_all_skill_infos(self.user_id)

        if not skill_infos:
            return ToolTaskResult(
                str_content="sys/skills/ 目录中没有可用的技能。",
                occur_error=False,
                json_content={"recommendations": [], "analysis": "未找到任何技能"}
            )

        # 获取 cancel_event
        cancel_event: asyncio.Event | None = kwargs.get("cancel_event", self.cancel_event)

        try:
            runner = SkillAdvisorRunner(
                user_id=self.user_id,
                parent_session_id=self.session_id,
                prompt=param.prompt,
                skill_infos=skill_infos,
                cancel_event=cancel_event,
            )
            result = await runner.run()

            # 格式化 str_content
            str_content = self._format_result(result)

            return ToolTaskResult(
                str_content=str_content,
                json_content=result.model_dump(),
                occur_error=False
            )
        except Exception as e:
            logfire.error(f"skill_advisor 工具执行错误: {e}")
            raise  # 重新抛出异常，由 base_agent 处理

    def _format_result(self, result) -> str:
        """格式化推荐结果为可读文本。"""
        lines = []

        if result.analysis:
            lines.append(f"**分析:** {result.analysis}")

        if result.recommendations:
            lines.append("\n**推荐技能:**")
            for i, rec in enumerate(result.recommendations, 1):
                lines.append(f"{i}. **{rec.skill_name}** ({rec.skill_path})")
                lines.append(f"   - {rec.relevance_reason}")
        else:
            lines.append("\n**未找到相关技能。**")

        return "\n".join(lines)


def construct_skill_advisor(
    config: SkillAdvisorConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 skill_advisor 工具实例。

    Args:
        config: 工具配置
        **kwargs: 注入参数（需要 user_id_for_scope, session_id）

    Returns:
        (工具参数, 工具闭包) 元组

    Raises:
        ValueError: 缺少必需参数时
    """
    user_id: UUID | None = kwargs.get("user_id")
    session_id: UUID | None = kwargs.get("session_id")
    cancel_event: asyncio.Event | None = kwargs.get("cancel_event")

    if user_id is None:
        raise ValueError("user_id_for_scope is required")
    if session_id is None:
        raise ValueError("session_id is required")

    tool = SkillAdvisorTool(
        config=config,
        user_id=user_id,
        session_id=session_id,
        cancel_event=cancel_event,
    )

    return (SKILL_ADVISOR_GENERATION_TOOL_PARAM, tool)


CONSTRUCTOR = {TOOL_NAME: construct_skill_advisor}