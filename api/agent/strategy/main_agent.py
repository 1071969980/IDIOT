import ujson
from asyncio import Event
from uuid import UUID
from typing import Any

from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaToolCall,
)
from openai.types.chat.chat_completion_message_param import (
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.chat import ChatCompletionMessageToolCall

from api.agent.base_agent import AgentBase
from api.chat.streaming_processor import StreamingProcessor
from api.agent.tools.type import ToolClosure
from api.agent.tools.data_model import ToolTaskResult
from api.chat.sql_stat.u2a_agent_msg.utils import (
    _U2AAgentMessageCreate,
)
from api.chat.sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryCreate,
)
from api.workflow.langfuse_prompt_template.main_agent import get_system_prompt


class MainAgent(AgentBase):
    """主 Agent 实现，封装现有的 main_agent_strategy 功能。"""

    def __init__(
        self,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        streaming_processor: StreamingProcessor,
        cancel_event: Event,
        service_name: str,
        tools: list[ChatCompletionToolParam],
        tool_call_function: dict[str, ToolClosure],
        loop_control: Any = None,
        **kwargs,
    ):
        super().__init__(user_id, 
                         session_id, 
                         session_task_id, 
                         cancel_event, 
                         tools,
                         tool_call_function,
                         loop_control)
        self.streaming_processor = streaming_processor
        self.service_name = service_name
        self.kwargs = kwargs

    async def on_agent_start(self, memories: list[ChatCompletionMessageParam]) -> None:
        """Agent 开始执行时初始化状态。"""
        # 重置消息计数器
        self._new_agent_msg_sub_seq_index_counter = 0
    async def prepare_kwargs(self, memories: list[ChatCompletionMessageParam]) -> dict:
        """准备 LLM 请求的 kwargs 参数。"""
        return {}

    async def on_generate_start(self) -> None:
        """开始生成内容时调用。"""
        self.streaming_processor.push_text_start_msg()

    async def on_generate_delta(self, delta: str) -> None:
        """接收到内容生成的每个 delta 时调用。"""
        self.streaming_processor.push_text_delta_msg(delta)

    async def on_generate_end(self) -> None:
        """生成过程结束时调用。"""
        self.streaming_processor.push_text_end_msg()

    async def on_generate_complete(self, content: str) -> None:
        """内容生成完成时记录文本消息。"""
        self._new_agent_messages_create.append(
            _U2AAgentMessageCreate(
                user_id=self.user_id,
                session_id=self.session_id,
                sub_seq_index=self._new_agent_msg_sub_seq_index_counter,
                message_type="text",
                content=content,
                status="complete",
                session_task_id=self.session_task_id,
            )
        )
        self._new_agent_msg_sub_seq_index_counter += 1

    async def on_tool_calls_start(self, tool_calls: list[ChoiceDeltaToolCall]) -> None:
        """工具调用开始时调用。"""
        pass

    async def on_tool_calls_start_batch(self, tool_calls: list[ChoiceDeltaToolCall], tool_func: dict[str, ToolClosure], tool_func_params: dict[str, dict]) -> None:
        """工具调用批次开始时调用。"""
        # 推送工具调用消息
        for tool_call in tool_calls:
            self.streaming_processor.push_tool_call_msg(tool_call)

    async def on_tool_call_start(self, tool_name: str, params: dict) -> None:
        """单个工具调用开始时调用。"""
        # 推送工具调用消息
        pass  # 这个在基类中已经处理了

    async def on_tool_call_complete(self, tool_name: str, result: ToolTaskResult) -> None:
        """单个工具调用完成时记录结果。"""
        # 记录工具调用消息
        self._new_agent_messages_create.append(
            _U2AAgentMessageCreate(
                user_id=self.user_id,
                session_id=self.session_id,
                sub_seq_index=self._new_agent_msg_sub_seq_index_counter,
                message_type="tool_call",
                json_content=result.model_dump_json(),
                content=tool_name,
                status="complete",
                session_task_id=self.session_task_id,
            )
        )
        self._new_agent_msg_sub_seq_index_counter += 1

        # 如果有子会话数据，记录子会话消息
        # u2a_session_link
        if result.u2a_session_link_data:
            self._new_agent_messages_create.append(
                _U2AAgentMessageCreate(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    sub_seq_index=self._new_agent_msg_sub_seq_index_counter,
                    message_type="u2a_session_link",
                    content=result.u2a_session_link_data.title,
                    json_content=result.u2a_session_link_data.model_dump_json(),
                    session_task_id=self.session_task_id,
                )
            )
            self._new_agent_msg_sub_seq_index_counter += 1
        # a2a_session_link
        if result.a2a_session_link_data:
            self._new_agent_messages_create.append(
                _U2AAgentMessageCreate(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    sub_seq_index=self._new_agent_msg_sub_seq_index_counter,
                    message_type="a2a_session_link",
                    content=result.a2a_session_link_data.goal,
                    json_content=result.a2a_session_link_data.model_dump_json(),
                    session_task_id=self.session_task_id,
                )
            )
            self._new_agent_msg_sub_seq_index_counter += 1

    async def on_tool_call_error(self, tool_name: str, error: Exception) -> None:
        """单个工具调用出错时调用。"""
        # 可以在这里记录错误日志
        pass

    async def on_tool_calls_complete_batch(self, tool_responses: list[ChatCompletionToolMessageParam]) -> None:
        """工具调用响应准备发送时调用。"""
        # 推送工具响应消息
        for tool_response in tool_responses:
            self.streaming_processor.push_tool_response_msg(tool_response)

    async def on_iteration_end(self, iteration: int, memories: list[ChatCompletionMessageParam]) -> None:
        """每次循环结束时调用。"""
        # 可以在这里进行循环级别的清理或记录
        pass

    async def on_agent_complete(self, memories: list[ChatCompletionMessageParam]) -> None:
        """Agent 完成时构建短期记忆记录。"""
        # 填充返回的记忆容器
        self._new_agent_memories_create.extend([
            _AgentShortTermMemoryCreate(
                user_id=self.user_id,
                session_id=self.session_id,
                content=ujson.dumps(mem, ensure_ascii=False),
                sub_seq_index=index,
                session_task_id=self.session_task_id,
            )
            for index, mem in enumerate(self._runtime_memories)
        ])