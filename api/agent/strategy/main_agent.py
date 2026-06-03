from asyncio import Event
from uuid import UUID
from typing import Any

from api.agent.base_agent import AgentBase, AgentRuntimeToolCallData
from api.chat.data_model import ToolInitializationResult
from api.chat.streaming_processor import StreamingProcessor
from api.chat.sql_stat.u2a_session_task.utils import (
    _U2ASessionTask,
    get_task
)
from api.agent.life_cycle_decorators import agent_decorator
from api.agent.tools.todo.lifecycle_hooks import inject_todo_context_on_agent_start, inject_todo_context_on_iteration_end
from api.agent.tools.summarization_compact.lifecycle_hooks import (
    inject_summarization_compact_context,
    inject_summarization_compact_closure,
)
from api.agent.system_reminder.tool_enable_status.decorators import (
    inject_tool_enable_status_reminder,
    inject_mcp_server_config_changed_reminder,
)
from api.agent.system_reminder.branch_changed.decorators import (
    inject_branch_changed_reminder,
)
from api.agent.tools.file_operations.lifecycle_hooks import (
    inject_file_hash_mismatch_reminder,
)

@agent_decorator(inject_file_hash_mismatch_reminder)
@agent_decorator(inject_todo_context_on_agent_start, inject_todo_context_on_iteration_end)
@agent_decorator(inject_summarization_compact_context, inject_summarization_compact_closure)
@agent_decorator(inject_tool_enable_status_reminder, inject_mcp_server_config_changed_reminder, inject_branch_changed_reminder)
class MainAgent(AgentBase):
    """主 Agent 实现，封装现有的 main_agent_strategy 功能。"""

    def __init__(
        self,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        session_branch_name: str,
        streaming_processor: StreamingProcessor,
        cancel_event: Event,
        service_name: str,
        tool_init_res: ToolInitializationResult,
        loop_control: Any = None,
        **kwargs,
    ):
        super().__init__(cancel_event,
                         tool_init_res,
                         loop_control)
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self.session_branch_name = session_branch_name
        self._session_task: _U2ASessionTask | None = None
        self.streaming_processor = streaming_processor
        self.service_name = service_name
        self.kwargs = kwargs

    @property
    async def session_task(self) -> _U2ASessionTask | None:
        if self._session_task is None:
            self._session_task = await get_task(self.session_task_id)
        return self._session_task

    async def on_generate_start(self) -> None:
        """开始生成内容时调用。"""
        await self.streaming_processor.push_text_start_msg()

    async def on_generate_normal_content_delta(self, delta: str) -> None:
        """接收到内容生成的每个 delta 时调用。"""
        await self.streaming_processor.push_text_delta_msg(delta)

    async def on_generate_reasoning_content_delta(self, delta: str) -> None:
        await self.streaming_processor.push_reasoning_delta_msg(delta)

    async def on_generate_complete(self, content: str, **kwargs) -> None:
        """内容生成完成时推送流结束消息。"""
        await self.streaming_processor.push_text_end_msg()

    async def on_tool_calls_start_batch(self, tool_exec_data: dict[UUID, AgentRuntimeToolCallData]) -> None:
        """工具调用批次开始时调用。"""
        # 推送工具调用消息
        for uuid, data in tool_exec_data.items():
            await self.streaming_processor.push_tool_call_msg(uuid, data["name"])

    async def on_tool_calls_complete_batch(self, tool_exec_data: dict[UUID, AgentRuntimeToolCallData]) -> None:
        """工具调用响应准备发送时调用。"""
        # 推送工具响应消息
        for uuid, data in tool_exec_data.items():
            task_result = data["task"].result() if data["task"] else None
            await self.streaming_processor.push_tool_response_msg(uuid, task_result)

    async def on_tool_call_start(self, tool_name: str, params: dict) -> None:
        """单个工具调用开始时调用。"""
        # 推送工具调用消息
        await super().on_tool_call_start(tool_name, params)

        params["metadata"] = {}
        params["metadata"]["user_id"] = self.user_id
        params["metadata"]["session_id"] = self.session_id
        params["metadata"]["session_task_id"] = self.session_task_id
