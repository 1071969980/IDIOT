"""
summarization_compact 工具的生命周期钩子

提供三个钩子：
- inject_summarization_compact_context: on_iteration_end 时注入压缩指导
- inject_summarization_compact_closure: prepare_tool_closures 时动态构造闭包
- inject_summarization_compact_tool_param: prepare_tool_params 时添加工具参数
"""

from typing import TYPE_CHECKING

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.life_cycle_decorators import lifecycle_hook

from .config_data_model import GENERATION_TOOL_PARAM, TOOL_NAME
from .messages import (
    build_compact_guidance,
    build_compact_instruction,
    format_tool_param_disclosure,
    should_compact,
)

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase
    from api.agent.tools.type import ToolClosure


@lifecycle_hook("on_iteration_end", position="after")
async def inject_summarization_compact_context(
    self: "AgentBase",
    iteration: int,
    mem_marker_name: str,
) -> None:
    """在 iteration 结束时检查 token 使用量，注入压缩指导或强制压缩。"""
    level = should_compact(self.input_new_token)

    if level == "no":
        # 确保 steering 中没有 summarization_compact
        self._tool_choice_steering.discard(TOOL_NAME)
        return

    if level == "must":
        # 强制压缩：设置 steering 并阻止模型结束循环
        self._tool_choice_steering.add(TOOL_NAME)
        self._tool_steering_block_stop = True

    # 注入消息到 memory_trails
    instruction = build_compact_instruction(level)
    guidance = build_compact_guidance()
    tool_disclosure = format_tool_param_disclosure()

    # 合并为一条 system 消息追加到标记
    msg = ChatCompletionSystemMessageParam(
        role="system",
        content=f"{instruction}\n\n{guidance}\n\n{tool_disclosure}",
    )
    self._memory_trails.append_to_marker(mem_marker_name, msg, to_agent_msg=False)


@lifecycle_hook("prepare_tool_closures", modifies_return=True, position="after")
async def inject_summarization_compact_closure(
    self: "AgentBase",
    closures: dict[str, "ToolClosure"],
    mem_marker_name: str,
) -> dict[str, "ToolClosure"]:
    """动态构造 summarization_compact 闭包并注入到工具闭包集合中。"""
    from .tool_closure import make_summarization_compact_closure

    closures[TOOL_NAME] = make_summarization_compact_closure(
        memory_trails=self._memory_trails,
        tool_choice_steering=self._tool_choice_steering,
        marker_name=mem_marker_name,
        agent=self,
    )
    return closures