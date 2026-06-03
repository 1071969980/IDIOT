"""
文件操作工具的生命周期钩子

在 Agent 循环迭代开始时检查文件哈希一致性，
如果检测到外部修改，注入系统提醒消息。
"""

from typing import TYPE_CHECKING

from openai.types.chat.chat_completion_system_message_param import ChatCompletionSystemMessageParam

from api.agent.life_cycle_decorators import lifecycle_hook
from api.agent.xml_marks_def import SYS_REMINDER_BLOCK_START, SYS_REMINDER_BLOCK_END
from .read_file.config_data_model import TOOL_NAME as READ_FILE_TOOL_NAME

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


@lifecycle_hook('on_iteration_start', position='before')
async def inject_file_hash_mismatch_reminder(
    self: "AgentBase",
    iteration: int,
    mem_marker_name: str,
) -> None:
    """检查文件是否被外部修改，如果是则注入提醒消息。"""

    # 1. 获取 read_file 工具的 hash_tracker
    read_tool = self.enable_tools_closure.get(READ_FILE_TOOL_NAME)
    if read_tool is None:
        return

    storage_backend = getattr(read_tool, 'storage_backend', None)
    if storage_backend is None:
        return

    tracker = getattr(storage_backend, 'hash_tracker', None)
    if tracker is None:
        return

    # 2. 检查外部编辑（静默失败）
    try:
        mismatches = await tracker.check_external_edits()
    except Exception:
        return

    if not mismatches:
        return

    # 3. 注入系统提醒
    file_list = "\n".join(f"  - {path}" for path, _, _ in mismatches)
    reminder = (
        f"{SYS_REMINDER_BLOCK_START}\n"
        f"以下文件在上次读取后被外部修改，请在需要时考虑重新读取以获取最新内容：\n"
        f"{file_list}\n"
        f"{SYS_REMINDER_BLOCK_END}"
    )
    msg = ChatCompletionSystemMessageParam(role="system", content=reminder)
    self._memory_trails.append_to_marker(mem_marker_name, msg)
