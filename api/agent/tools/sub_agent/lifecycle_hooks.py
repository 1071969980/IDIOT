from typing import TYPE_CHECKING, cast

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.life_cycle_decorators import lifecycle_hook
from api.agent.xml_marks_def import SYS_REMINDER_BLOCK_START, SYS_REMINDER_BLOCK_END
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_keys import (
    StorageSnapshotKeys,
)
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    update_branch_storage_snapshot,
)

from .config_data_model import TOOL_NAME

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


def _format_first_time_message(
    definitions: dict,
) -> str:
    lines = "\n".join(
        f"  - {name}: {defn.description}"
        for name, defn in sorted(definitions.items())
    )
    return (
        f"{SYS_REMINDER_BLOCK_START}\n"
        f"当前有以下子代理可用，你可以通过 {TOOL_NAME} 工具调用它们：\n"
        f"{lines}\n"
        f"{SYS_REMINDER_BLOCK_END}\n"
    )


def _format_changed_message(
    definitions: dict,
    added_names: set[str],
    removed_names: set[str],
) -> str:
    parts: list[str] = []
    if added_names:
        added_lines = "\n".join(
            f"  + {name}: {definitions[name].description}"
            for name in sorted(added_names)
        )
        parts.append(f"新增子代理：\n{added_lines}")
    if removed_names:
        removed_lines = "\n".join(
            f"  - {name}" for name in sorted(removed_names)
        )
        parts.append(f"已移除子代理：\n{removed_lines}")
    parts.append("当前可用的完整子代理列表：")
    parts.append(
        "\n".join(
            f"  - {name}: {defn.description}"
            for name, defn in sorted(definitions.items())
        )
    )
    return (
        f"{SYS_REMINDER_BLOCK_START}\n"
        + "\n".join(parts)
        + f"\n{SYS_REMINDER_BLOCK_END}\n"
    )


@lifecycle_hook("on_agent_start", position="before")
async def inject_sub_agent_list_reminder(
    self: "AgentBase",
    mem_marker_name: str,
):
    from api.agent.strategy.main_agent import MainAgent
    from api.agent.tools.sub_agent.constructor import SubAgentTool

    if TOOL_NAME not in self.enable_tools_closure:
        return

    sub_agent_tool = self.enable_tools_closure[TOOL_NAME]
    if not isinstance(sub_agent_tool, SubAgentTool):
        return

    definitions = await sub_agent_tool._ensure_definitions_loaded()
    current_names = set(definitions.keys())

    # 读取 storage_snapshot 中缓存的名称列表
    if (
        not hasattr(self, "session_task")
        or not callable(getattr(self, "session_task"))
        or not hasattr(self, "user_id")
    ):
        return
    agent = cast("MainAgent", self)
    session_task = await agent.session_task
    if session_task is None or session_task.storage_snapshot is None:
        return

    cached_names = set(
        session_task.storage_snapshot.get(StorageSnapshotKeys.SUB_AGENT_NAMES, [])
    )

    if current_names == cached_names:
        return

    # 构造提醒消息
    if not cached_names:
        reminder = _format_first_time_message(definitions)
    else:
        added = current_names - cached_names
        removed = cached_names - current_names
        reminder = _format_changed_message(definitions, added, removed)

    msg = ChatCompletionSystemMessageParam(content=reminder, role="system")
    self._memory_trails.append_to_marker(mem_marker_name, msg)

    # 更新 storage_snapshot
    try:
        await update_branch_storage_snapshot(
            session_id=agent.session_id,
            user_id=agent.user_id,
            branch_name=agent.session_branch_name,
            update_fn=lambda snapshot: (
                snapshot.update(
                    {StorageSnapshotKeys.SUB_AGENT_NAMES: sorted(current_names)}
                )
                or True
            ),
        )
    except Exception:
        pass
