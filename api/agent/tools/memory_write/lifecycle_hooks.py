"""
memory_write 工具的生命周期钩子

提供一个钩子：
- inject_memory_write_context: on_agent_start 时注入记忆写入上下文
"""

from typing import TYPE_CHECKING, cast

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.life_cycle_decorators import lifecycle_hook
from api.agent.tools.bash.config_data_model import TOOL_NAME as BASH_TOOL_NAME
from api.agent.tools.file_operations.list_directory.config_data_model import TOOL_NAME as LIST_DIR_TOOL_NAME
from api.agent.tools.file_operations.read_file.config_data_model import TOOL_NAME as READ_FILE_TOOL_NAME
from api.agent.tools.file_operations.write_file.config_data_model import TOOL_NAME as WRITE_FILE_TOOL_NAME
from api.agent.tools.memory_write.memory_discovery import discover_memory_index_files
from api.agent.tools.memory_write.messages import build_write_context_msg

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


@lifecycle_hook("on_agent_start", position="after")
async def inject_memory_write_context(
    self: "AgentBase",
    mem_marker_name: str,
) -> None:
    from api.agent.strategy.mem_write_agent import MemWriteAgent
    """在 Agent 启动时注入记忆写入上下文，包含工作要求和 MEMORY.md 索引。"""
    agent = cast(MemWriteAgent, self)

    memory_indices = await discover_memory_index_files(
        allowed_rel_dirs=agent.tool_init_res.allowed_rel_dirs_in_juicefs_for_tool,
        session_id=agent.session_id,
        user_id=agent.user_id,
    )

    context_msg = ChatCompletionSystemMessageParam(
        role="system",
        content=build_write_context_msg(memory_indices),
    )
    agent._memory_trails.append_to_marker(
        mem_marker_name, context_msg, is_new=True, to_agent_msg=False,
    )

    # 允许读写工具 + bash
    write_tools = {READ_FILE_TOOL_NAME, WRITE_FILE_TOOL_NAME, LIST_DIR_TOOL_NAME, BASH_TOOL_NAME}
    agent.set_tool_choice_steering(write_tools)
