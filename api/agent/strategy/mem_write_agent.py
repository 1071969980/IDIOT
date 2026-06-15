"""MemWriteAgent — 记忆写入 Agent

在主 Agent 执行后异步运行，负责根据交互内容更新记忆文件。
使用标准文件系统工具和 Bash 工具完成记忆文件的增删改。
"""

from asyncio import Event
from uuid import UUID

from api.agent.base_agent import AgentBase
from api.agent.life_cycle_decorators import agent_decorator
from api.agent.tools.memory.config_data_model import MemoryToolScope
from api.agent.tools.memory.write.lifecycle_hooks import inject_memory_write_context
from api.agent.tools.summarization_compact.lifecycle_hooks import (
    inject_summarization_compact_context,
    inject_summarization_compact_closure,
)
from api.chat.data_model import ToolInitializationResult
from api.chat.sql_stat.u2a_session_task.utils import get_task


@agent_decorator(inject_memory_write_context)
@agent_decorator(inject_summarization_compact_context, inject_summarization_compact_closure)
class MemWriteAgent(AgentBase):
    """记忆写入 Agent，继承 AgentBase，注册 context 钩子。"""

    def __init__(
        self,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        cancel_event: Event,
        tool_init_res: ToolInitializationResult,
        memory_scope: MemoryToolScope,
        **kwargs,
    ):
        super().__init__(cancel_event, tool_init_res)
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self.memory_scope = memory_scope
        self._session_task = None

    @property
    async def session_task(self):
        if self._session_task is None:
            self._session_task = await get_task(self.session_task_id)
        return self._session_task

    async def on_tool_call_start(self, tool_name: str, params: dict) -> None:
        """单个工具调用开始时注入元数据。"""
        await super().on_tool_call_start(tool_name, params)
        params["metadata"] = {}
        params["metadata"]["user_id"] = self.user_id
        params["metadata"]["session_id"] = self.session_id
        params["metadata"]["session_task_id"] = self.session_task_id
