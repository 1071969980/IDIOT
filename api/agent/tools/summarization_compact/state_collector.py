"""
压缩后状态收集与注入模块

在 summarization_compact 工具执行后，收集运行时状态并注入到 breakpoint 之后。

收集的状态包括：
1. 工具启用状态
2. TODO 列表
3. 已加载技能文档
4. 关键文件内容（由 LLM 通过 key_files 参数指定）
"""

import asyncio
import contextlib
from typing import TYPE_CHECKING, cast

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.tools.skills.load_skill.config_data_model import TOOL_NAME as LOAD_SKILL_TOOL_NAME

from api.agent.xml_marks_def import SYS_REMINDER_BLOCK_START, SYS_REMINDER_BLOCK_END

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase
    from api.agent.memory_trails.trails import MemoryTrails


async def collect_and_inject_post_compression_state(
    agent: "AgentBase",
    memory_trails: "MemoryTrails",
    marker_name: str,
    key_files: list[str] | None,
    cancel_event: asyncio.Event | None = None,
) -> None:
    """收集运行时状态并注入到压缩断点之后。

    每类状态独立收集，任何一类失败不影响其他类。
    所有注入的消息出现在 context_breakpoint 之后，压缩后仍然有效。
    """
    # 1. 工具启用状态（纯内存，瞬时）
    tool_status_msg = _collect_tool_enable_status(agent)
    if tool_status_msg:
        memory_trails.append_to_marker(marker_name, tool_status_msg)

    # 取消检查点：每次 I/O 步骤前检查
    if cancel_event is not None and cancel_event.is_set():
        return

    # 2. TODO 列表
    todo_msg = await _collect_todo_state(agent)
    if todo_msg:
        memory_trails.append_to_marker(marker_name, todo_msg)

    if cancel_event is not None and cancel_event.is_set():
        return

    # 3. 已加载技能文档
    skills_msg = await _collect_skills_state(agent, cancel_event=cancel_event)
    if skills_msg:
        memory_trails.append_to_marker(marker_name, skills_msg)

    if cancel_event is not None and cancel_event.is_set():
        return

    # 4. 关键文件内容
    if key_files:
        files_msg = await _collect_key_files(agent, key_files, cancel_event=cancel_event)
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
    """收集 TODO 列表状态。"""
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
    cancel_event: asyncio.Event | None = None,
) -> ChatCompletionSystemMessageParam | None:
    """压缩恢复时校验并重建已加载技能状态。

    顺序：① 失效缓存并重新扫描定义 → ② 据此清理 LOADED_SKILLS → ③ 重新读取仍加载技能的内容。
    若 ② 导致 LOADED_SKILLS 变化，或 ③ 有可恢复文档，则构造 system 消息；
    该 agent 没有 load_skill 工具时跳过本段。
    """
    from api.agent.tools.skills.load_skill.constructor import LoadSkillTool
    from api.agent.tools.skills.load_skill.utils import _format_skill_info

    load_skill_tool = agent.enable_tools_closure.get(LOAD_SKILL_TOOL_NAME)
    if not isinstance(load_skill_tool, LoadSkillTool):
        return None

    # ① 失效缓存并重新扫描定义（拿到最新盘上状态）
    try:
        fresh_infos = await load_skill_tool.reload_skill_infos(cancel_event=cancel_event)
    except Exception:
        return None

    # ② 按刷新后的披露名集合清理 LOADED_SKILLS
    removed, remaining = await load_skill_tool.cleanup_loaded_skills(
        set(fresh_infos.keys())
    )

    # ③ 重新读取仍加载技能的完整定义
    skill_blocks: list[str] = []
    for skill_name in remaining:
        # 逐技能检查取消
        if cancel_event is not None and cancel_event.is_set():
            break
        with contextlib.suppress(Exception):
            skill_def = await load_skill_tool.get_skill_definition(
                skill_name, cancel_event=cancel_event,
            )
            if skill_def is not None:
                skill_blocks.append(_format_skill_info(skill_def))

    # 无变更且无可恢复文档 → 不产生消息
    if not removed and not skill_blocks:
        return None

    parts: list[str] = []
    if removed:
        removed_lines = "\n".join(f"  - {name}" for name in sorted(removed))
        parts.append(
            "## 已加载技能变更（压缩恢复）\n\n"
            "以下此前加载的技能已不可用（被删除/改名/重名冲突变化），"
            "已从已加载列表移除：\n"
            + removed_lines
        )
    if skill_blocks:
        parts.append(
            "## 已加载技能文档（压缩恢复）\n\n"
            "以下是你已加载的技能，内容已重新加载：\n\n"
            + "\n\n---\n\n".join(skill_blocks)
        )

    content = (
        f"{SYS_REMINDER_BLOCK_START}\n"
        + "\n\n".join(parts)
        + f"\n{SYS_REMINDER_BLOCK_END}\n"
    )
    return ChatCompletionSystemMessageParam(role="system", content=content)


async def _collect_key_files(
    agent: "AgentBase",
    file_paths: list[str],
    cancel_event: asyncio.Event | None = None,
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
        # 逐文件前检查取消
        if cancel_event is not None and cancel_event.is_set():
            break
        with contextlib.suppress(Exception):
            content, first_line, total_lines = await storage_backend.read_file(
                file_path, cancel_event=cancel_event,
            )
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
    """格式化文件内容。"""
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
