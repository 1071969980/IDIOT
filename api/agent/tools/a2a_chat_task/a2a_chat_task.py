from typing import Any, Literal
from uuid import UUID

from openai.types.chat import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure

from .sql_stat.a2a_session.utils import (
    get_session,
    session_exists,
)
from .sql_stat.a2a_session_short_term_memory.utils import (
    get_session_short_term_memories_by_session,
)
from .sql_stat.a2a_session_task.utils import (
    task_exists,
)


async def get_system_prompt() -> str:
    return ""

async def try_compress_short_term_memory():
    pass

async def init_tools(
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
) -> tuple[list[ChatCompletionToolParam], dict[str, ToolClosure]]:
    tools = []
    closures = {}
    return tools, closures

async def a2a_chat_task(
                    session_id: UUID,
                    session_task_id: UUID,
                    proactive_side: Literal["A", "B"],
                    params: dict[str, Any]):
    # principle: 任务需要断言世界的状态

    # 检查session的存在性
    if not await session_exists(session_id) or not await task_exists(session_task_id):
        raise ValueError("Session or Task not exists")

    session_row = await get_session(session_id)
    proactive_user_id = session_row.user_a_id if proactive_side == "A" else session_row.user_b_id
    passive_user_id = session_row.user_b_id if proactive_side == "A" else session_row.user_a_id
    
    # 检查params
    goal = params.get("goal")
    if not goal:
        raise ValueError("Goal is required")
    
    # 尝试压缩模型记忆
    await try_compress_short_term_memory()
    
    # 收集短期记忆
    ## 构造系统提示
    system_prompt = await get_system_prompt()

    sys_mem = ChatCompletionSystemMessageParam(
        content=system_prompt,
        role="system",
    )

    ## 收集短期记忆
    short_term_memories_row = await get_session_short_term_memories_by_session(session_id, table_side="A")

    short_term_mem = [
        row.content
        for row in short_term_memories_row
    ]

    tools, closures = await init_tools(proactive_user_id, session_id, session_task_id)
