# api/agent/tools/skills/skill_advisor/submit_result_constructor.py

"""skill_advisor 专用的 submit_result 工具动态构造。"""

from dataclasses import dataclass

from pydantic import BaseModel, Field
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.dynamic_tool_DI.constructor import construct_tool
from api.agent.tools.type import ToolClosure
from api.agent.tools.skills.data_model import SkillRecommendation


@dataclass
class SkillAdvisorResultContainer:
    """skill_advisor 结果容器，存储结构化结果。"""

    result: list[SkillRecommendation] | None = None
    analysis: str = ""
    called: bool = False


class SubmitSkillAdvisorResultParamDefine(BaseModel):
    """submit_result 工具的参数定义。"""

    recommendations: list[SkillRecommendation] = Field(
        default_factory=list,
        description="推荐的技能列表，每个包含 skill_name, skill_path, relevance_reason"
    )
    analysis: str = Field(
        default="",
        description="问题分析和技能匹配的简要分析"
    )


def construct_submit_result_tool(
    result_container: SkillAdvisorResultContainer
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 skill_advisor 专用的 submit_result 工具。

    使用动态工具注入和结果容器模式，直接存储结构化结果。

    Args:
        result_container: 用于存储结构化结果的可变容器

    Returns:
        (工具参数, 工具闭包) 元组
    """
    async def submit_result_callback(param: BaseModel) -> None:
        if not isinstance(param, SubmitSkillAdvisorResultParamDefine):
            raise TypeError(
                f"Expected SubmitSkillAdvisorResultParamDefine, got {type(param).__name__}"
            )
        if result_container.called:
            raise RuntimeError("submit_result 只能调用一次")

        result_container.result = param.recommendations
        result_container.analysis = param.analysis
        result_container.called = True

    return construct_tool(
        tool_name="submit_result",
        tool_description=(
            "提交技能推荐结果。"
            "必须调用此工具返回最终答案，包含推荐的技能列表和分析说明。"
            "此工具只能调用一次。"
        ),
        tool_param_model=SubmitSkillAdvisorResultParamDefine,
        call_back=submit_result_callback
    )