from asyncio import Event
from uuid import UUID

from openai.types.chat.chat_completion_message_param import (
    ChatCompletionMessageParam,
)

from api.agent.memory_tree import MemoryTree
from api.agent.strategy.main_agent import MainAgent
from api.chat.data_model import ToolInitializationResult
from api.chat.sql_stat.u2a_agent_msg.utils import (
    _U2AAgentMessageCreate,
)
from api.chat.sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryCreate,
)
from api.chat.streaming_processor import StreamingProcessor


async def main_agent_strategy(
    user_id: UUID,
    session_id: UUID,
    session_task_id: UUID,
    branch_name: str,
    memories: list[ChatCompletionMessageParam],
    tool_init_res: ToolInitializationResult,
    service_name: str,
    streaming_processor: StreamingProcessor,
    cancel_event: Event,
    **kwargs,
) -> tuple[list[_AgentShortTermMemoryCreate], list[_U2AAgentMessageCreate]]:
    """
    主 Agent 策略函数。

    接收线性记忆列表，内部构建 MemoryTree 并注入 agent。
    """
    # 创建 MainAgent 实例
    agent = MainAgent(
        user_id=user_id,
        session_id=session_id,
        session_task_id=session_task_id,
        branch_name=branch_name,
        streaming_processor=streaming_processor,
        cancel_event=cancel_event,
        service_name=service_name,
        tool_init_res=tool_init_res,
        **kwargs,
    )

    # 从线性记忆构建 MemoryTree 并注入 agent
    tree = MemoryTree()
    tree.load_from_linear(memories, branch_name)
    agent._memory_tree = tree

    # 执行 Agent 循环
    await agent.run(branch_name, service_name)

    # 显式提取 DB 数据
    mem_creates = tree.extract_db_create_data(
        branch_name, user_id, session_id, session_task_id,
    )
    agent_messages = tree.extract_agent_messages(
        branch_name, user_id, session_id, session_task_id,
    )
    return mem_creates, agent_messages
