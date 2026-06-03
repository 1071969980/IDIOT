"""
压缩后状态收集与注入模块

在 summarization_compact 工具执行后，收集运行时状态并注入到 breakpoint 之后，
确保压缩后的 LLM 能无缝继续任务。

收集的状态包括：
1. 工具启用状态
2. TODO 列表
3. 已加载技能文档
4. 关键文件内容（由 LLM 通过 key_files 参数指定）
"""

import contextlib
from typing import TYPE_CHECKING, cast
from uuid import UUID

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.xml_marks_def import SYS_REMINDER_BLOCK_START, SYS_REMINDER_BLOCK_END

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase
    from api.agent.memory_trails.trails import MemoryTrails


async def collect_and_inject_post_compression_state(
    agent: "AgentBase",
    memory_trails: "MemoryTrails",
    marker_name: str,
    key_files: list[str] | None,
) -> None:
    """收集运行时状态并注入到压缩断点之后。

    每类状态独立收集，任何一类失败不影响其他类。
    所有注入的消息出现在 context_breakpoint 之后，压缩后仍然有效。
    """
    # 1. 工具启用状态
    tool_status_msg = _collect_tool_enable_status(agent)
    if tool_status_msg:
        memory_trails.append_to_marker(marker_name, tool_status_msg)

    # 2. TODO 列表
    todo_msg = await _collect_todo_state(agent)
    if todo_msg:
        memory_trails.append_to_marker(marker_name, todo_msg)

    # 3. 已加载技能文档
    skills_msg = await _collect_skills_state(agent)
    if skills_msg:
        memory_trails.append_to_marker(marker_name, skills_msg)

    # 4. 关键文件内容
    if key_files:
        files_msg = await _collect_key_files(agent, key_files)
        if files_msg:
            memory_trails.append_to_marker(marker_name, files_msg)


def _collect_tool_enable_status(
    agent: "AgentBase",
) -> ChatCompletionSystemMessageParam | None:
    """收集工具启用状态。复用已有的格式化函数。"""
    if not agent.enable_explicit_tools_name:
        return None

    from api.agent.system_reminder.tool_enable_status.decorators import (
        _format_tool_enable_status_reminder,
    )

    content = _format_tool_enable_status_reminder(agent.enable_explicit_tools_name)
    return ChatCompletionSystemMessageParam(role="system", content=content)


async def _collect_todo_state(
    agent: "AgentBase",
) -> ChatCompletionSystemMessageParam | None:
    """收集 TODO 列表状态。参考 inject_todo_context 的访问模式。"""
    from api.agent.tools.todo.config_data_model import TOOL_NAME as TODO_TOOL_NAME
    from api.agent.tools.todo.lifecycle_hooks import _format_todos_for_context

    if TODO_TOOL_NAME not in agent.enable_tools_closure:
        return None

    todo_tool = agent.enable_tools_closure[TODO_TOOL_NAME]
    if not hasattr(todo_tool, "storage_backend"):
        return None

    try:
        todos = await todo_tool.storage_backend.get_all_todos()
    except Exception:
        return None

    if not todos:
        return None

    content = _format_todos_for_context(todos)
    return ChatCompletionSystemMessageParam(role="system", content=content)


async def _collect_skills_state(
    agent: "AgentBase",
) -> ChatCompletionSystemMessageParam | None:
    """收集已加载技能文档。从 storage_snapshot 读取技能列表，重新加载 SKILL.md 内容。"""
    # 需要 MainAgent 特有属性
    if not hasattr(agent, "user_id") or not hasattr(agent, "session_id"):
        return None

    user_id: UUID = agent.user_id  # type: ignore
    session_id: UUID = agent.session_id  # type: ignore
    branch_name: str | None = getattr(agent, "session_branch_name", None)
    if branch_name is None:
        return None

    from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_keys import StorageSnapshotKeys
    from api.agent.tools.skills.definition_loader import load_skill_definition
    from api.agent.tools.skills.load_skill.utils import _format_skill_info
    from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
        get_branch_storage_snapshot,
    )

    # 读取 storage_snapshot 获取已加载技能列表
    try:
        _, snapshot = await get_branch_storage_snapshot(
            session_id=session_id,
            user_id=user_id,
            branch_name=branch_name,
        )
    except Exception:
        return None

    loaded_skills: list[str] = snapshot.get(StorageSnapshotKeys.LOADED_SKILLS, [])
    if not loaded_skills:
        return None

    # 重新加载每个技能的 SKILL.md 内容
    skill_blocks: list[str] = []
    for skill_name in loaded_skills:
        with contextlib.suppress(Exception):
            skill_def = await load_skill_definition(user_id, skill_name)
            if skill_def is not None:
                skill_blocks.append(_format_skill_info(skill_def))

    if not skill_blocks:
        return None

    content = (
        f"{SYS_REMINDER_BLOCK_START}\n"
        "## 已加载技能文档（压缩恢复）\n\n"
        "以下是你之前加载的技能，内容已从原始文件重新加载：\n\n"
        + "\n\n---\n\n".join(skill_blocks)
        + f"\n{SYS_REMINDER_BLOCK_END}\n"
    )
    return ChatCompletionSystemMessageParam(role="system", content=content)


async def _collect_key_files(
    agent: "AgentBase",
    file_paths: list[str],
) -> ChatCompletionSystemMessageParam | None:
    """收集关键文件内容。复用 read_file 工具的 storage_backend。"""
    from api.agent.tools.file_operations.read_file.config_data_model import TOOL_NAME as READ_FILE_TOOL_NAME
    from api.agent.tools.file_operations.read_file.constructor import ReadFileTool

    if READ_FILE_TOOL_NAME not in agent.enable_tools_closure:
        return None

    read_file_tool = agent.enable_tools_closure[READ_FILE_TOOL_NAME]
    read_file_tool = cast(ReadFileTool, read_file_tool)
    if not hasattr(read_file_tool, "storage_backend"):
        return None

    storage_backend = read_file_tool.storage_backend
    file_blocks: list[str] = []

    for file_path in file_paths:
        with contextlib.suppress(Exception):
            content, first_line, total_lines = await storage_backend.read_file(file_path)
            formatted = _format_file_content(file_path, content, first_line, total_lines)
            file_blocks.append(formatted)

    if not file_blocks:
        return None

    content = (
        f"{SYS_REMINDER_BLOCK_START}\n"
        "## 关键文件内容（压缩恢复）\n\n"
        "以下是你指定的关键文件，内容已重新加载：\n\n"
        + "\n\n".join(file_blocks)
        + f"\n{SYS_REMINDER_BLOCK_END}\n"
    )
    return ChatCompletionSystemMessageParam(role="system", content=content)


def _format_file_content(
    file_path: str,
    content: str,
    first_line_number: int,
    total_lines: int,
) -> str:
    """格式化文件内容，参考 ReadFileTool._format_output 的风格。"""
    lines = content.split("\n")
    if not lines or (len(lines) == 1 and not lines[0]):
        return f"文件内容：{file_path}\n文件为空"

    formatted_lines = []
    for i, line in enumerate(lines):
        if len(line) > 1000:
            line = line[:1000] + "... [line be truncated]"
        line_number = i + first_line_number
        formatted_line = (f"{line_number}→").rjust(5, " ") + line
        formatted_lines.append(formatted_line)

    last_line_number = first_line_number + len(lines) - 1
    header = (
        f"文件内容：{file_path}\n"
        f"读取行数：{first_line_number}-{last_line_number} / 共{total_lines}行\n"
    )
    return header + "\n" + "\n".join(formatted_lines)
