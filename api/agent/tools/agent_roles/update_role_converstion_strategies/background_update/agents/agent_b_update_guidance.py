"""
Agent B：更新对话总结指导文件

功能：根据更新后的对话策略，更新对话总结指导文件

执行流程：
1. 获取并编译 Langfuse 提示词模板
2. 构造两个动态工具：read_guidance_part 和 edit_guidance
3. 构造 OpenAI 格式的记忆（memories）
4. 初始化 AgentBase
5. 执行 Agent（带重试逻辑，最多3次）
6. 检查工具调用状态

设计文档参考：
- docs/dev_spec/agent_role_conversation_strategies_background_update_task_spec_docs/background_update_task_spec_design.md#21-整体流程
"""

from asyncio import Event
from typing import Callable
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel, Field

from api.agent.base_agent import AgentBase
from api.agent.tools.type import ToolClosure
from api.agent.tools.dynamic_tool_DI.constructor import construct_tool
from api.workflow.langfuse_prompt_template.constant import _get_prompt_from_langfuse
from ..models import (
    AgentBResult,
    MAX_TOOL_CALL_RETRIES,
)
from api.agent.tools.read_file.utils import read_from_string
from api.agent.tools.edit_file.utils import edit_string
import logfire


# ========== 工具参数定义 ==========

class ReadGuidancePartToolParam(BaseModel):
    """读取对话总结指导的部分内容"""
    offset: int = Field(default=0, ge=0, description="起始行号（从 0 开始）")
    limit: int = Field(default=100, ge=1, le=1000, description="读取的行数")


class EditGuidanceToolParam(BaseModel):
    """编辑对话总结指导内容"""
    old_text: str = Field(..., description="要替换的原始文本")
    new_text: str = Field(..., description="替换后的新文本")
    replace_all: bool = Field(default=False, description="是否替换所有出现")


# ========== Agent 函数实现 ==========

async def run_agent_b_update_guidance(
    updated_strategies: str,
    original_guidance: str,
    review_suggestions: str | None,
    service_name: str,
    agent_b_working_guidance: dict[str, str],
    agent_b_result: AgentBResult
) -> None:
    """
    Agent B: 更新对话总结指导文件

    执行流程:
    1. 获取并编译 Langfuse 提示词模板
    2. 构造两个动态工具：read_guidance_part 和 edit_guidance
    3. 构造 OpenAI 格式的记忆（memories）
    4. 初始化 AgentBase
    5. 执行 Agent（带重试逻辑）
    6. 检查工具调用状态

    参数:
        updated_strategies: Agent A 更新后的对话策略（作为上下文）
        original_guidance: 原始的对话总结指导内容
        review_suggestions: Agent C 的审查建议（第一轮为 None）
        service_name: LLM 服务名称
        agent_b_working_guidance: 工作容器（可变 dict，由工具闭包捕获并修改）
        agent_b_result: 结果容器（TypedDict，存储执行状态和最终结果）

    返回:
        None（结果通过 agent_b_result 容器传递）
    """

    # ========== 步骤1: 获取并编译提示词 ==========
    prompt = _get_prompt_from_langfuse("agent-role-update/update-guidance")
    if not prompt:
        raise ValueError("Langfuse prompt not found: agent-role-update/update-guidance")

    system_prompt = prompt.compile(
        updated_strategies=updated_strategies,
        original_guidance=original_guidance,
        review_suggestions=review_suggestions or ""
    )

    # ========== 步骤2: 构造动态工具 ==========
    tool_define_list: list[ChatCompletionToolParam] = []
    tool_call_function: dict[str, ToolClosure] = {}

    # 工具1: read_guidance_part
    async def read_guidance_callback(param: BaseModel) -> None:
        # 类型检查
        if not isinstance(param, ReadGuidancePartToolParam):
            error_msg = (
                f"Expected ReadGuidancePartToolParam, got {type(param).__name__}",
            )
            raise TypeError(error_msg)
        # 调用同步函数 read_from_string
        read_from_string(
            agent_b_working_guidance["value"],
            offset=param.offset,
            limit=param.limit,
            add_line_numbers=True
        )

    tool_define_1, tool_closure_1 = construct_tool(
        tool_name="read_guidance_part",
        tool_description=(
            "读取对话总结指导文件的部分内容，帮助了解当前指导的具体内容。"
            "可以通过 offset 和 limit 参数控制读取的范围。"
        ),
        tool_param_model=ReadGuidancePartToolParam,
        call_back=read_guidance_callback
    )
    tool_define_list.append(tool_define_1)
    tool_call_function["read_guidance_part"] = tool_closure_1

    # 工具2: edit_guidance
    async def edit_guidance_callback(param: BaseModel) -> None:
        # 类型检查
        if not isinstance(param, EditGuidanceToolParam):
            error_msg = (
                f"Expected EditGuidanceToolParam, got {type(param).__name__}",
            )
            raise TypeError(error_msg)

        """编辑对话总结指导的工作变量"""
        try:
            agent_b_working_guidance["value"] = edit_string(
                string=agent_b_working_guidance["value"],
                old_text=param.old_text,
                new_text=param.new_text,
                replace_all=param.replace_all
            )
            agent_b_result["tool_called"] = True
            logfire.info("agent-role-update::agent_b_edit_success")
        except ValueError as e:
            logfire.error("agent-role-update::agent_b_edit_failed", error=str(e))
            raise

    tool_define_2, tool_closure_2 = construct_tool(
        tool_name="edit_guidance",
        tool_description=(
            "编辑对话总结指导的内容。使用 old_text 和 new_text 参数进行文本替换。"
            "如果 old_text 在文件中出现多次，需要设置 replace_all=True。"
        ),
        tool_param_model=EditGuidanceToolParam,
        call_back=edit_guidance_callback
    )
    tool_define_list.append(tool_define_2)
    tool_call_function["edit_guidance"] = tool_closure_2

    # ========== 步骤3: 构造 memories ==========
    memories: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": (
                "请根据更新后的对话策略，更新对话总结指导文件。\n\n"
                "执行步骤：\n"
                "1. 首先使用 read_guidance_part 工具了解当前指导的内容\n"
                "2. 然后使用 edit_guidance 工具进行必要的修改\n"
                "3. 可以多次调用 edit_guidance 工具完成多个修改\n\n"
                "注意事项：\n"
                "- 确保指导内容与更新后的策略保持一致\n"
                "- 保持原有的格式和结构\n"
                "- 如果有审查建议，请根据建议进行修改"
            )
        }
    ]

    # ========== 步骤4: 初始化 AgentBase ==========
    agent = AgentBase(
        cancel_event=Event(),
        tools=tool_define_list,
        tool_call_function=tool_call_function
    )

    # ========== 步骤5: 执行 Agent（带重试逻辑） ==========
    for attempt in range(MAX_TOOL_CALL_RETRIES):
        if attempt > 0:
            logfire.warning(
                "agent-role-update::agent_b_retry",
                attempt=attempt,
                max_retries=MAX_TOOL_CALL_RETRIES
            )
            # 重置工作容器和状态
            agent_b_working_guidance["value"] = original_guidance
            agent_b_result["tool_called"] = False

        with logfire.span("agent-role-update::agent_b_execution", attempt=attempt):
            new_memories, new_messages = await agent.run(
                memories=memories,
                service_name=service_name,
                thinking=True
            )

        # 检查是否成功调用工具
        if agent_b_result["tool_called"]:
            logfire.info("agent-role-update::agent_b_success")
            break

    # ========== 步骤6: 检查最终状态 ==========
    if not agent_b_result["tool_called"]:
        logfire.error("agent-role-update::agent_b_failed_after_retries")
        raise RuntimeError(f"Agent B failed to call edit_guidance tool after {MAX_TOOL_CALL_RETRIES} attempts")
