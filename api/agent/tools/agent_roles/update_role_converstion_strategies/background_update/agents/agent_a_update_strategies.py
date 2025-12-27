"""
Agent A：更新对话策略文件

功能：根据用户的更新请求和审查建议，更新对话策略文件

执行流程：
1. 获取并编译 Langfuse 提示词模板
2. 构造两个动态工具：read_strategies_part 和 edit_strategies
3. 构造 OpenAI 格式的记忆（memories）
4. 初始化 AgentBase
5. 执行 Agent（带重试逻辑，最多3次）
6. 检查工具调用状态

设计文档参考：
- docs/dev_spec/agent_role_conversation_strategies_background_update_task_spec_docs/background_update_task_spec_design.md#21-整体流程
"""

from asyncio import Event
from typing import Callable
from uuid import UUID
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel, Field

from api.agent.base_agent import AgentBase
from api.agent.tools.type import ToolClosure
from api.agent.tools.dynamic_tool_DI.constructor import construct_tool
from api.workflow.langfuse_prompt_template.constant import _get_prompt_from_langfuse
from ..models import (
    AgentAResult,
    MAX_TOOL_CALL_RETRIES,
)
from api.agent.tools.read_file.utils import read_from_string
from api.agent.tools.edit_file.utils import edit_string
import logfire


# ========== 工具参数定义 ==========

class ReadStrategiesPartToolParam(BaseModel):
    """读取对话策略的部分内容"""
    offset: int = Field(default=0, ge=0, description="起始行号（从 0 开始）")
    limit: int = Field(default=100, ge=1, le=1000, description="读取的行数")


class EditStrategiesToolParam(BaseModel):
    """编辑对话策略内容"""
    old_text: str = Field(..., description="要替换的原始文本")
    new_text: str = Field(..., description="替换后的新文本")
    replace_all: bool = Field(default=False, description="是否替换所有出现（默认只替换第一个）")


# ========== Agent 函数实现 ==========

async def run_agent_a_update_strategies(
    original_strategies: str,
    strategies_update_list: str,
    review_suggestions: str | None,
    service_name: str,
    agent_a_working_strategies: dict[str, str],
    agent_a_result: AgentAResult
) -> None:
    """
    Agent A: 更新对话策略文件

    执行流程:
    1. 获取并编译 Langfuse 提示词模板
    2. 构造两个动态工具：read_strategies_part 和 edit_strategies
    3. 构造 OpenAI 格式的记忆（memories）
    4. 初始化 AgentBase
    5. 执行 Agent（带重试逻辑）
    6. 检查工具调用状态

    参数:
        original_strategies: 原始的对话策略内容
        strategies_update_list: 格式化后的更新请求文本
        review_suggestions: Agent C 的审查建议（第一轮为 None）
        service_name: LLM 服务名称
        agent_a_working_strategies: 工作容器（可变 dict，由工具闭包捕获并修改）
        agent_a_result: 结果容器（TypedDict，存储执行状态和最终结果）

    返回:
        None（结果通过 agent_a_result 容器传递）
    """

    # ========== 步骤1: 获取并编译提示词 ==========
    prompt = _get_prompt_from_langfuse("agent-role-update/update-strategies")
    if not prompt:
        raise ValueError("Langfuse prompt not found: agent-role-update/update-strategies")

    system_prompt = prompt.compile(
        original_strategies=original_strategies,
        strategies_update_cache=strategies_update_list,
        review_suggestions=review_suggestions or ""
    )

    # ========== 步骤2: 构造动态工具 ==========
    tool_define_list: list[ChatCompletionToolParam] = []
    tool_call_function: dict[str, ToolClosure] = {}

    # 工具1: read_strategies_part
    async def read_strategies_callback(param: BaseModel) -> None:
        # 类型检查
        if not isinstance(param, ReadStrategiesPartToolParam):
            error_msg = (
                f"Expected ReadStrategiesPartToolParam, got {type(param).__name__}",
            )
            raise TypeError(error_msg)
        # 调用同步函数 read_from_string（不使用返回值，结果会通过 construct_tool 返回）
        read_from_string(
            agent_a_working_strategies["value"],
            offset=param.offset,
            limit=param.limit,
            add_line_numbers=True
        )

    tool_define_1, tool_closure_1 = construct_tool(
        tool_name="read_strategies_part",
        tool_description=(
            "读取对话策略文件的部分内容，帮助了解当前策略的具体内容。"
            "可以通过 offset 和 limit 参数控制读取的范围。"
        ),
        tool_param_model=ReadStrategiesPartToolParam,
        call_back=read_strategies_callback
    )
    tool_define_list.append(tool_define_1)
    tool_call_function["read_strategies_part"] = tool_closure_1

    # 工具2: edit_strategies
    async def edit_strategies_callback(param: BaseModel) -> None:
        # 类型检查
        if not isinstance(param, EditStrategiesToolParam):
            error_msg = (
                f"Expected EditStrategiesToolParam, got {type(param).__name__}",
            )
            raise TypeError(error_msg)

        """编辑对话策略的工作变量"""
        try:
            agent_a_working_strategies["value"] = edit_string(
                string=agent_a_working_strategies["value"],
                old_text=param.old_text,
                new_text=param.new_text,
                replace_all=param.replace_all
            )
            agent_a_result["tool_called"] = True
            logfire.info("agent-role-update::agent_a_edit_success")
        except ValueError as e:
            logfire.error("agent-role-update::agent_a_edit_failed", error=str(e))
            raise

    tool_define_2, tool_closure_2 = construct_tool(
        tool_name="edit_strategies",
        tool_description=(
            "编辑对话策略的内容。使用 old_text 和 new_text 参数进行文本替换。"
            "如果 old_text 在文件中出现多次，需要设置 replace_all=True。"
        ),
        tool_param_model=EditStrategiesToolParam,
        call_back=edit_strategies_callback
    )
    tool_define_list.append(tool_define_2)
    tool_call_function["edit_strategies"] = tool_closure_2

    # ========== 步骤3: 构造 memories ==========
    memories: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": (
                "请根据提供的更新请求，更新对话策略文件。\n\n"
                "执行步骤：\n"
                "1. 首先使用 read_strategies_part 工具了解当前策略的内容\n"
                "2. 然后使用 edit_strategies 工具进行必要的修改\n"
                "3. 可以多次调用 edit_strategies 工具完成多个修改\n\n"
                "注意事项：\n"
                "- 保持原有的格式和结构\n"
                "- 确保更新后的策略连贯一致\n"
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
                "agent-role-update::agent_a_retry",
                attempt=attempt,
                max_retries=MAX_TOOL_CALL_RETRIES
            )
            # 重置工作容器和状态
            agent_a_working_strategies["value"] = original_strategies
            agent_a_result["tool_called"] = False

        with logfire.span("agent-role-update::agent_a_execution", attempt=attempt):
            new_memories, new_messages = await agent.run(
                memories=memories,
                service_name=service_name,
                thinking=True
            )

        # 检查是否成功调用工具
        if agent_a_result["tool_called"]:
            logfire.info("agent-role-update::agent_a_success")
            break

    # ========== 步骤6: 检查最终状态 ==========
    if not agent_a_result["tool_called"]:
        logfire.error("agent-role-update::agent_a_failed_after_retries")
        raise RuntimeError(f"Agent A failed to call edit_strategies tool after {MAX_TOOL_CALL_RETRIES} attempts")
