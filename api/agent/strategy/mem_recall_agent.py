"""MemRecallAgent — 记忆召回 Agent

在主 Agent 执行前同步运行，负责从记忆文件系统中检索相关记忆内容，
通过 return_memory_recall 工具将检索结果注入到主 Agent 的 major Marker。
"""

from asyncio import Event
from uuid import UUID

from api.agent.base_agent import AgentBase
from api.agent.life_cycle_decorators import agent_decorator
from api.agent.tools.memory_recall.lifecycle_hooks import (
    inject_memory_recall_context,
    inject_return_memory_recall_closure,
)
from api.agent.tools.summarization_compact.lifecycle_hooks import (
    inject_summarization_compact_context,
    inject_summarization_compact_closure,
)
from api.chat.data_model import ToolInitializationResult
from api.chat.sql_stat.u2a_session_task.utils import get_task


@agent_decorator(inject_memory_recall_context, inject_return_memory_recall_closure)
@agent_decorator(inject_summarization_compact_context, inject_summarization_compact_closure)
class MemRecallAgent(AgentBase):
    """记忆召回 Agent，继承 AgentBase，注册 context + closure 两个钩子。"""

    def __init__(
        self,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        cancel_event: Event,
        tool_init_res: ToolInitializationResult,
        **kwargs,
    ):
        super().__init__(cancel_event, tool_init_res)
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self._session_task = None

    @property
    async def session_task(self):
        if self._session_task is None:
            self._session_task = await get_task(self.session_task_id)
        return self._session_task

    @property
    def recommend_memory_recall_target_marker(self) -> str:
        """推荐的目标 Marker，默认 "major"（即主 Agent 的工作 Marker）。"""
        return "major"

    async def on_tool_call_start(self, tool_name: str, params: dict) -> None:
        """单个工具调用开始时注入元数据。"""
        await super().on_tool_call_start(tool_name, params)
        params["metadata"] = {}
        params["metadata"]["user_id"] = self.user_id
        params["metadata"]["session_id"] = self.session_id
        params["metadata"]["session_task_id"] = self.session_task_id
