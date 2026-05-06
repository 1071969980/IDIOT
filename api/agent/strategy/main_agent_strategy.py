from asyncio import Event
from uuid import UUID

from openai.types.chat.chat_completion_message_param import (
    ChatCompletionMessageParam,
)
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.memory_trails import MemoryTrails
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
    主 Agent 策略函数。

    接收线性记忆列表，内部构建 MemoryTrails 并注入 agent。
    """
    # 创建 MainAgent 实例
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

    # 从线性记忆构建 MemoryTrails 并注入 agent
    agent._system_mem = system_mem
    trails = MemoryTrails()
    trails.create_marker("base", memories)
    trails.fork_marker("base", "major")
    agent._memory_trails = trails

    # 执行 Agent 循环
    await agent.run("major", service_name)

    # 显式提取 DB 数据
    mem_creates = trails.extract_db_create_data(
        "major", user_id, session_id, session_task_id,
    )
    agent_messages = trails.extract_agent_messages(
        "major", user_id, session_id, session_task_id,
    )
    return mem_creates, agent_messages
