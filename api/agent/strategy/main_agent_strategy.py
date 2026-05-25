import asyncio
from pathlib import PurePosixPath

from asyncio import Event
from uuid import UUID

import logfire
from openai.types.chat.chat_completion_message_param import (
    ChatCompletionMessageParam,
)
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from uuid6 import uuid7

from api.agent.memory_trails import MemoryTrails
from api.agent.strategy.main_agent import MainAgent
from api.agent.strategy.mem_recall_agent import MemRecallAgent
from api.agent.strategy.mem_write_agent import MemWriteAgent
from api.chat.data_model import ToolInitializationResult
from api.chat.session_event_streaming.event_types import (
    SessionMemRecallStartedEvent,
    SessionMemRecallCompletedEvent,
    SessionMemWriteStartedEvent,
    SessionMemWriteCompletedEvent,
    SessionMemRecallStartedEventPayload,
    SessionMemRecallCompletedEventPayload,
    SessionMemWriteStartedEventPayload,
    SessionMemWriteCompletedEventPayload,
)
from api.chat.session_event_streaming.publisher import publish_SSE_session_event
from api.chat.sql_stat.u2a_agent_msg.utils import (
    _U2AAgentMessageCreate,
)
from api.chat.sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryCreate,
)
from api.chat.streaming_processor import StreamingProcessor
from api.agent.tools.file_operations.storage_backend.juicefs_sdk import JuiceFSSdkBackend
from api.user_pod_scheduler.constants import JUICEFS_MOUNT_PATH


async def _has_valid_memory_indices(
    tool_init_res: ToolInitializationResult,
    session_id: UUID,
    user_id: UUID,
) -> bool:
    """检查是否存在有效的记忆索引文件（MEMORY.md）。

    只有在 allowed_rel_dirs 包含 sys/memory/ 路径且对应目录下
    存在 MEMORY.md 文件时才返回 True。
    """
    memory_root = PurePosixPath("sys/memory")
    memory_rel_dirs: list[PurePosixPath] = []
    for rel_dir in tool_init_res.allowed_rel_dirs_in_juicefs_for_tool:
        try:
            PurePosixPath(rel_dir).relative_to(memory_root)
        except ValueError:
            continue
        memory_rel_dirs.append(PurePosixPath(rel_dir))

    if not memory_rel_dirs:
        return False

    backend = JuiceFSSdkBackend(
        session_id=session_id,
        user_id=user_id,
        allowed_rel_dirs_in_juicefs_for_tool=list(tool_init_res.allowed_rel_dirs_in_juicefs_for_tool),
    )
    for rel_dir in memory_rel_dirs:
        memory_md_path = PurePosixPath(JUICEFS_MOUNT_PATH) / rel_dir / "MEMORY.md"
        try:
            if await backend.file_exists(str(memory_md_path)):
                return True
        except Exception:
            continue
    return False


def _should_run_memory_write(tool_init_res: ToolInitializationResult) -> bool:
    """判断是否需要执行记忆写入。独立于召回判断。"""
    memory_root = PurePosixPath("sys/memory")
    for rel_dir in tool_init_res.allowed_rel_dirs_in_juicefs_for_tool:
        try:
            PurePosixPath(rel_dir).relative_to(memory_root)
        except ValueError:
            continue
        return True
    return False


def _fallback_recall_msg() -> ChatCompletionSystemMessageParam:
    """记忆召回失败时的降级提示消息。"""
    return ChatCompletionSystemMessageParam(
        role="system",
        content="记忆召回不可用，请继续执行当前任务。",
    )


async def main_agent_strategy(
    user_id: UUID,
    session_id: UUID,
    session_task_id: UUID,
    session_branch_name: str,
    system_mem: ChatCompletionSystemMessageParam,
    memories: list[ChatCompletionMessageParam],
    tool_init_res: ToolInitializationResult,
    service_name: str,
    streaming_processor: StreamingProcessor,
    cancel_event: Event,
    **kwargs,
) -> tuple[list[_AgentShortTermMemoryCreate], list[_U2AAgentMessageCreate]]:
    """
    主 Agent 策略函数（三阶段流程）。

    阶段1：记忆召回（同步前置，条件执行）
    阶段2：主 Agent 执行
    阶段3：后台记忆写入（asyncio Task，条件独立于阶段1）
    """
    trails = MemoryTrails()
    trails.create_marker("base", memories)
    trails.fork_marker("base", "major")

    # === 阶段1：记忆召回（同步前置） ===
    should_recall = await _has_valid_memory_indices(tool_init_res, session_id, user_id)
    if should_recall:
        recall_agent = MemRecallAgent(
            user_id=user_id,
            session_id=session_id,
            session_task_id=session_task_id,
            cancel_event=cancel_event,
            tool_init_res=tool_init_res,
        )
        recall_agent._memory_trails = trails
        recall_uuid = str(uuid7())
        trails.fork_marker("base", f"mem_recall:{recall_uuid}")

        await publish_SSE_session_event(
            session_id,
            SessionMemRecallStartedEvent(
                session_id=session_id,
                payload=SessionMemRecallStartedEventPayload(
                    session_task_id=session_task_id,
                ),
            ),
        )
        try:
            with logfire.span("memory_recall"):
                await recall_agent.run(f"mem_recall:{recall_uuid}", service_name)
        except Exception:
            logfire.error("记忆召回异常")
            trails.append_to_marker("major", _fallback_recall_msg(), is_new=True)
        await publish_SSE_session_event(
            session_id,
            SessionMemRecallCompletedEvent(
                session_id=session_id,
                payload=SessionMemRecallCompletedEventPayload(
                    session_task_id=session_task_id,
                    has_exception=False,
                ),
            ),
        )

    # === 阶段2：主 Agent 执行 ===
    agent = MainAgent(
        user_id=user_id,
        session_id=session_id,
        session_task_id=session_task_id,
        session_branch_name=session_branch_name,
        streaming_processor=streaming_processor,
        cancel_event=cancel_event,
        service_name=service_name,
        tool_init_res=tool_init_res,
        **kwargs,
    )
    agent._system_mem = system_mem
    agent._memory_trails = trails

    await agent.run("major", service_name)

    # === 阶段3：后台记忆写入 ===
    should_write = _should_run_memory_write(tool_init_res)
    if should_write:
        write_agent = MemWriteAgent(
            user_id=user_id,
            session_id=session_id,
            session_task_id=session_task_id,
            cancel_event=cancel_event,
            tool_init_res=tool_init_res,
        )
        write_agent._memory_trails = trails
        write_uuid = str(uuid7())
        trails.fork_marker("base", f"mem_write:{write_uuid}")

        async def _run_write_background():
            await publish_SSE_session_event(
                session_id,
                SessionMemWriteStartedEvent(
                    session_id=session_id,
                    payload=SessionMemWriteStartedEventPayload(
                        session_task_id=session_task_id,
                    ),
                ),
            )
            try:
                with logfire.span("memory_write"):
                    await write_agent.run(f"mem_write:{write_uuid}", service_name)
            except Exception:
                logfire.error("记忆写入异常")
            await publish_SSE_session_event(
                session_id,
                SessionMemWriteCompletedEvent(
                    session_id=session_id,
                    payload=SessionMemWriteCompletedEventPayload(
                        session_task_id=session_task_id,
                        has_exception=False,
                    ),
                ),
            )

        asyncio.create_task(_run_write_background())

    # 仅从 major Marker 提取数据，MemWriteAgent 的对话不需要持久化到 DB
    mem_creates = trails.extract_db_create_data(
        "major", user_id, session_id, session_task_id,
    )
    agent_messages = trails.extract_agent_messages(
        "major", user_id, session_id, session_task_id,
    )
    return mem_creates, agent_messages
