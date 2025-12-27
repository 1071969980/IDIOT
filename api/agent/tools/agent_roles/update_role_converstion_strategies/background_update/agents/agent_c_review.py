"""
Agent C：审查更新结果

功能：审查对话策略和总结指导的更新内容，给出评分和修改建议

执行流程：
1. 生成 strategies_diff 和 guidance_diff
2. 获取并编译 Langfuse 提示词模板
3. 构造动态工具：submit_review_result
4. 构造 OpenAI 格式的记忆（memories）
5. 初始化 AgentBase
6. 执行 Agent（不需要重试，只执行一次）

设计文档参考：
- docs/dev_spec/agent_role_conversation_strategies_background_update_task_spec_docs/background_update_task_spec_design.md#21-整体流程
"""

from asyncio import Event
import difflib
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel, Field

from api.agent.base_agent import AgentBase
from api.agent.tools.type import ToolClosure
from api.agent.tools.dynamic_tool_DI.constructor import construct_tool
from api.workflow.langfuse_prompt_template.constant import _get_prompt_from_langfuse
from ..models import (
    AgentCResult,
)
import logfire


# ========== 辅助函数 ==========

def generate_diff(original: str, updated: str, filename: str = "file") -> str:
    """生成 unified diff 格式"""
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"Original {filename}",
        tofile=f"Updated {filename}",
        lineterm=""
    )
    return "".join(diff)


# ========== 工具参数定义 ==========

class SubmitReviewToolParam(BaseModel):
    """提交审查结果"""
    score: int = Field(..., ge=0, le=100, description="审查分数（0-100）")
    suggestions: str = Field(default="", description="修改建议（如果评分低于 80 分）")


# ========== Agent 函数实现 ==========

async def run_agent_c_review(
    original_strategies: str,
    original_guidance: str,
    updated_strategies: str,
    updated_guidance: str,
    service_name: str,
    agent_c_result: AgentCResult
) -> None:
    """
    Agent C: 审查更新结果

    执行流程:
    1. 生成 strategies_diff 和 guidance_diff
    2. 获取并编译 Langfuse 提示词模板
    3. 构造动态工具：submit_review_result
    4. 构造 OpenAI 格式的记忆（memories）
    5. 初始化 AgentBase
    6. 执行 Agent（不需要重试，只执行一次）

    参数:
        original_strategies: 原始的对话策略
        original_guidance: 原始的对话总结指导
        updated_strategies: Agent A 更新后的对话策略
        updated_guidance: Agent B 更新后的对话总结指导
        service_name: LLM 服务名称
        agent_c_result: 结果容器（TypedDict，存储审查分数和建议）

    返回:
        None（结果通过 agent_c_result 容器传递）
    """

    # ========== 步骤1: 生成 diff ==========
    strategies_diff = generate_diff(
        original_strategies,
        updated_strategies,
        "conversation_strategies.md"
    )
    guidance_diff = generate_diff(
        original_guidance,
        updated_guidance,
        "concluding_guidance.md"
    )

    logfire.info(
        "agent-role-update::agent_c_diff_generated",
        strategies_diff_lines=strategies_diff.count('\n'),
        guidance_diff_lines=guidance_diff.count('\n')
    )

    # ========== 步骤2: 获取并编译提示词 ==========
    prompt = _get_prompt_from_langfuse("agent-role-update/review-updates")
    if not prompt:
        raise ValueError("Langfuse prompt not found: agent-role-update/review-updates")

    system_prompt = prompt.compile(
        strategies_diff=strategies_diff,
        guidance_diff=guidance_diff
    )

    # ========== 步骤3: 构造动态工具 ==========
    async def submit_review_callback(param: BaseModel) -> None:
        # 类型检查
        if not isinstance(param, SubmitReviewToolParam):
            error_msg = (
                f"Expected SubmitReviewToolParam, got {type(param).__name__}",
            )
            raise TypeError(error_msg)

        """提交审查结果"""
        agent_c_result["score"] = param.score
        agent_c_result["suggestions"] = param.suggestions
        logfire.info(
            "agent-role-update::agent_c_review_submitted",
            score=param.score,
            has_suggestions=bool(param.suggestions)
        )

    tool_define, tool_closure = construct_tool(
        tool_name="submit_review_result",
        tool_description=(
            "提交对更新内容的审查结果。"
            "根据更新的质量给出 0-100 分的评分，"
            "并给出具体的修改建议（如果评分低于 80 分）。"
        ),
        tool_param_model=SubmitReviewToolParam,
        call_back=submit_review_callback
    )

    # ========== 步骤4: 构造 memories ==========
    memories: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": (
                "请审查对话策略和总结指导的更新内容。\n\n"
                "审查标准：\n"
                "1. 更新是否准确反映了用户的请求\n"
                "2. 内容是否连贯一致\n"
                "3. 格式是否规范\n"
                "4. 是否存在遗漏或错误\n\n"
                "评分标准：\n"
                "- 80-100 分：优秀，可以通过\n"
                "- 60-79 分：良好，但需要修改\n"
                "- 0-59 分：不合格，需要重新修改\n\n"
                "审查完成后，请调用 submit_review_result 工具提交结果。"
            )
        }
    ]

    # ========== 步骤5: 初始化 AgentBase ==========
    agent = AgentBase(
        cancel_event=Event(),
        tools=[tool_define],
        tool_call_function={
            "submit_review_result": tool_closure
        }
    )

    # ========== 步骤6: 执行 Agent ==========
    with logfire.span("agent-role-update::agent_c_execution"):
        new_memories, new_messages = await agent.run(
            memories=memories,
            service_name=service_name,
            thinking=True
        )

    logfire.info(
        "agent-role-update::agent_c_completed",
        score=agent_c_result["score"],
        pass_threshold=agent_c_result["score"] >= 80
    )
