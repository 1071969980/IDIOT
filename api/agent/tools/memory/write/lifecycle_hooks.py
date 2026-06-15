"""
memory_write 生命周期钩子

提供一个钩子：
- inject_memory_write_context: on_agent_start 时注入记忆写入上下文
"""

from typing import TYPE_CHECKING, cast

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.life_cycle_decorators import lifecycle_hook

from ..memory_discovery import discover_memory_index_files
from .messages import build_write_context_msg

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


@lifecycle_hook("on_agent_start", position="after")
async def inject_memory_write_context(
    self: "AgentBase",
    mem_marker_name: str,
) -> None:
    from api.agent.strategy.mem_write_agent import MemWriteAgent
    """在 Agent 启动时注入记忆写入上下文。"""
    agent = cast(MemWriteAgent, self)

    memory_indices = await discover_memory_index_files(
        memory_dirs=agent.memory_scope.memory_dirs,
        session_id=agent.session_id,
        scope=agent.memory_scope.to_file_ops_scope(),
    )

    context_msg = ChatCompletionSystemMessageParam(
        role="system",
        content=build_write_context_msg(memory_indices),
    )
    agent._memory_trails.append_to_marker(
        mem_marker_name, context_msg, is_new=True,
        to_agent_msg=False,
    )
