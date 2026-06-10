"""
memory_recall 生命周期钩子

提供两个钩子：
- inject_memory_recall_context: on_agent_start 时注入记忆召回上下文
- inject_return_memory_recall_closure: prepare_tool_closures 时动态构造闭包
"""

from typing import TYPE_CHECKING, cast

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.life_cycle_decorators import lifecycle_hook

from ..memory_discovery import _get_juicefs_backend, discover_memory_index_files
from .config_data_model import TOOL_NAME
from .messages import build_recall_context_parts

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase
    from api.agent.tools.type import ToolClosure


@lifecycle_hook("on_agent_start", position="after")
async def inject_memory_recall_context(
    self: "AgentBase",
    mem_marker_name: str,
) -> None:
    from api.agent.strategy.mem_recall_agent import MemRecallAgent
    """在 Agent 启动时注入记忆召回上下文。"""
    agent = cast(MemRecallAgent, self)

    memory_indices = await discover_memory_index_files(
        memory_dirs=agent.memory_scope.memory_dirs,
        session_id=agent.session_id,
        scope=agent.memory_scope.to_file_ops_scope(),
    )

    context_parts = build_recall_context_parts(memory_indices)
    context_msg = ChatCompletionSystemMessageParam(
        role="system",
        content="\n\n".join(context_parts),
    )
    agent._memory_trails.append_to_marker(
        mem_marker_name, context_msg, is_new=True,
        to_agent_msg=False,
    )


@lifecycle_hook("prepare_tool_closures", modifies_return=True, position="after")
async def inject_return_memory_recall_closure(
    self: "AgentBase",
    closures: dict[str, "ToolClosure"],
    mem_marker_name: str,
) -> dict[str, "ToolClosure"]:
    from api.agent.strategy.mem_recall_agent import MemRecallAgent
    """动态构造 return_memory_recall 闭包。"""
    from .tool_closure import make_return_memory_recall_closure

    agent = cast(MemRecallAgent, self)

    juicefs_backend = _get_juicefs_backend(
        session_id=agent.session_id,
        scope=agent.memory_scope.to_file_ops_scope(),
    )
    closures[TOOL_NAME] = make_return_memory_recall_closure(
        memory_trails=agent._memory_trails,
        juicefs_backend=juicefs_backend,
    )
    return closures
