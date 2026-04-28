"""
summarization_compact 工具的生命周期钩子

在 on_iteration_end 时根据 token 使用情况，注入压缩指导消息或强制压缩。
"""

from typing import TYPE_CHECKING

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.life_cycle_decorators import lifecycle_hook

from .config_data_model import TOOL_NAME
from .messages import (
    build_compact_guidance,
    build_compact_instruction,
    format_tool_param_disclosure,
    should_compact,
)

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


@lifecycle_hook("on_iteration_end", position="after")
async def inject_summarization_compact_context(
    self: "AgentBase",
    iteration: int,
    branch_name: str,
) -> None:
    """在 iteration 结束时检查 token 使用量，注入压缩指导或强制压缩。"""
    level = should_compact(self.input_new_token)

    if level == "no":
        # 确保 steering 中没有 summarization_compact
        self._tool_choice_steering.discard(TOOL_NAME)
        return

    if level == "must":
        # 强制压缩：设置 steering
        self._tool_choice_steering.add(TOOL_NAME)

    # 注入消息到 memory_tree
    instruction = build_compact_instruction(level)
    guidance = build_compact_guidance()
    tool_disclosure = format_tool_param_disclosure()

    # 合并为一条 system 消息追加到分支
    msg = ChatCompletionSystemMessageParam(
        role="system",
        content=f"{instruction}\n\n{guidance}\n\n{tool_disclosure}",
    )
    self._memory_tree.append_to_branch(branch_name, msg, to_agent_msg=False)
