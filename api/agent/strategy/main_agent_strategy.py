from asyncio import Event
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from openai.types.chat.chat_completion_message_param import (
    ChatCompletionMessageParam,
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.chat.streaming_processor import StreamingProcessor
from api.agent.tools.type import ToolClosure
from api.chat.sql_stat.u2a_agent_msg.utils import (
   _U2AAgentMessageCreate,
)
from api.chat.sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryCreate,
)
from api.agent.strategy.main_agent import MainAgent


async def main_agent_strategy(
    user_id: UUID,
    session_id: UUID,
    session_task_id: UUID,
    memories: list[ChatCompletionMessageParam],
    tools: list[ChatCompletionToolParam],
    tool_call_function: dict[str, ToolClosure],
    service_name: str,
    streaming_processor: StreamingProcessor,
    cancel_event: Event,
    **kwargs,
) -> tuple[list[_AgentShortTermMemoryCreate], list[_U2AAgentMessageCreate]]:
    """
    主 Agent 策略函数 - 兼容性包装器。

    此函数保持原有接口不变，内部使用新的面向对象实现。
    """
    # 创建 MainAgent 实例
    agent = MainAgent(
        user_id=user_id,
        session_id=session_id,
        session_task_id=session_task_id,
        streaming_processor=streaming_processor,
        cancel_event=cancel_event,
        service_name=service_name,
        tools=tools,
        tool_call_function=tool_call_function,
        **kwargs,
    )

    # 执行 Agent 循环，传入 service_name 参数
    return await agent.run(memories, service_name)