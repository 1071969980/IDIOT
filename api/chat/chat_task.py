import asyncio
from asyncio import Event
from uuid import UUID

from openai.types.chat.chat_completion_system_message_param import ChatCompletionSystemMessageParam
from openai.types.chat.chat_completion_user_message_param import ChatCompletionUserMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.tool_factory import ToolFactory
from api.agent.strategy.main_agent_strategy import main_agent_strategy
from api.redis.pubsub import subscribe_to_event
from api.workflow.langfuse_prompt_template.main_agent import get_system_prompt

from .sql_stat.u2a_agent_msg.utils import (
    insert_agent_messages_from_list,
    delete_agent_messages_by_session_task
)
from .sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryResponse,
    create_agent_short_term_memories_from_list,
    get_agent_short_term_memories_by_session,
    delete_agent_short_term_memories_by_session_task
)
from .sql_stat.u2a_session_task.utils import (
    _U2ASessionTask,
    update_task_status,
)
from .sql_stat.u2a_user_msg.utils import (
    _U2AUserMessage,
    update_user_message_session_task_by_ids,
    update_user_message_status_by_ids,
)
from .sql_stat.u2a_user_short_term_memory.utils import (
    _UserShortTermMemoryCreate,
    _UserShortTermMemoryResponse,
    create_user_short_term_memories_from_list,
    get_next_seq_index,
    get_user_short_term_memories_by_session,
    delete_user_short_term_memories_by_session_task
)
from .streaming_processor import StreamingProcessor
from api.agent.tools.type import ToolClosure
from api.agent.session_agent_config.config_data_model import SessionAgentConfig
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    get_session_config_by_session_id,
)


async def handel_processing_session_task(tasks: list[_U2ASessionTask]):
    pass

async def try_compress_short_term_memory():
    pass

async def query_short_term_memory(
    session_id: UUID,
) -> list[dict]:
    _user_mem = await get_user_short_term_memories_by_session(session_id)
    _agent_mem = await get_agent_short_term_memories_by_session(session_id)

    # 按session_task_id 分组 _user_mem,并每组按 seq_index 进行排序
    grouped_user_memories : dict[UUID | None, list[_UserShortTermMemoryResponse]] = {}
    for memory in _user_mem:
        session_task_id = memory.session_task_id
        if session_task_id not in grouped_user_memories:
            grouped_user_memories[session_task_id] = []
        grouped_user_memories[session_task_id].append(memory)
    for group in grouped_user_memories.values():
        group.sort(key=lambda x: x.seq_index)

    # 将_agent_mem 按 session_task_id 进行分组，并每组按sub_seq_index 进行排序
    grouped_agent_memories : dict[UUID | None, list[_AgentShortTermMemoryResponse]] = {}
    for memory in _agent_mem:
        session_task_id = memory.session_task_id
        if session_task_id not in grouped_agent_memories:
            grouped_agent_memories[session_task_id] = []
        grouped_agent_memories[session_task_id].append(memory)
    for group in grouped_agent_memories.values():
        group.sort(key=lambda x: x.sub_seq_index)

    # 计算每个task的最大user记忆seq_index用于排序
    task_max_seq_index = {}
    for session_task_id, user_memories in grouped_user_memories.items():
        if user_memories:
            task_max_seq_index[session_task_id] = max(mem.seq_index for mem in user_memories)

    # 检查agent记忆中的task_id是否在user记忆中存在（使用集合运算提高效率）
    user_task_ids = set(grouped_user_memories.keys())
    invalid_agent_tasks = {agent_task_id for agent_task_id in grouped_agent_memories.keys()
                             if agent_task_id is not None and agent_task_id not in user_task_ids}
    if invalid_agent_tasks:
        raise ValueError(f"Agent记忆中存在task_id {invalid_agent_tasks}，但在User记忆中找不到对应的task")

    # 收集所有session_task_id（包括没有user记忆但有agent记忆的）
    all_session_task_ids = set(grouped_user_memories.keys()) | set(grouped_agent_memories.keys())

    # 按照task的user记忆seq_index最大值升序排序（None排在最前面）
    sorted_session_task_ids = sorted(
        all_session_task_ids,
        key=lambda task_id: task_max_seq_index.get(task_id, -1) if task_id is not None else -1,
    )

    # 合并记忆为一维列表
    merged_memories : list[dict] = []

    for session_task_id in sorted_session_task_ids:
        # 添加该task的user记忆
        if session_task_id in grouped_user_memories:
            merged_memories.extend(
                [mem.content for mem in grouped_user_memories[session_task_id]],
            )

        # 添加该task的agent记忆
        if session_task_id in grouped_agent_memories:
            merged_memories.extend(
                [mem.content for mem in grouped_agent_memories[session_task_id]],
            )

    return merged_memories

async def init_tools(
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID
) -> tuple[list[ChatCompletionToolParam], dict[str, ToolClosure]]:
    # 获得会话agent配置
    session_config_row = await get_session_config_by_session_id(session_id)
    if session_config_row:
        session_config = SessionAgentConfig.model_validate(session_config_row.config)
    else:
        session_config = SessionAgentConfig()

    tools_config = session_config.tools_config

    # 使用工厂初始化工具
    tool_factory = ToolFactory(
        user_id=user_id,
        session_id=session_id,
        session_task_id=session_task_id,
    )

    ret1 = []
    ret2 = {}

    for tool_name, tool_config in tools_config.items():
        tool_completion_param, tool_call_function = await tool_factory.prerare_tool(tool_name, tool_config)
        ret1.append(tool_completion_param)
        ret2[tool_name] = tool_call_function

    return ret1, ret2

async def session_chat_task(
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        llm_service: str,
        pending_messages: list[_U2AUserMessage],
        during_processing_tasks: list[_U2ASessionTask],
):
    # 初始化处理管道
    streaming_processor = StreamingProcessor(
        task_uuid=session_task_id,
    )

    """
    处理所有会话中的待回复消息。
    """
    try:
        # 更新消息状态

        ## 将所有待处理消息的所属任务更新
        await update_user_message_session_task_by_ids(
            [msg.id for msg in pending_messages],
            session_task_id,
        )

        ## 将所有待处理消息标记为"处理中"
        update_success = await update_user_message_status_by_ids(
            [msg.id for msg in pending_messages],
            "agent_working_for_user",
        )

        # 注册Redis取消信号的监听
        cancel_event = Event()
        redis_cancel_channel = f"session_task_canceling:{session_task_id}"
        wait_cancel_task = asyncio.create_task(
            subscribe_to_event(redis_cancel_channel, cancel_event),
        )

        # 检查是否有正在运行的任务，并处理，可能涉及到更改先前的消息记录和追加pending_messages
        await handel_processing_session_task(during_processing_tasks)

        # 尝试压缩模型记忆
        await try_compress_short_term_memory()

        # 收集AI短期记忆
        ## 构造系统提示
        system_prompt = get_system_prompt(
            production=True,
            label="session_task",
            version=1,
        )

        if not system_prompt:
            raise ValueError("系统提示未配置")

        sys_mem = ChatCompletionSystemMessageParam(
            content=system_prompt,
            role="system",
        )

        ## 从数据库中构造用户和agent短期记忆
        user_and_agent_memories_json = await query_short_term_memory(session_id)

        ## 添加当次任务的user消息
        new_user_mem = [
            ChatCompletionUserMessageParam(
                content=msg.content,
                role="user",
            )
            for msg in pending_messages
        ]
        
        ## 合并这些记忆
        mem = []
        mem.append(sys_mem)
        mem.extend(user_and_agent_memories_json)
        mem.extend(new_user_mem)

        # 执行Agent
        tools, tool_call_function = await init_tools(
            user_id=user_id,
            session_id=session_id,
            session_task_id=session_task_id,
        )

        new_agent_memories_create, new_agent_messages_create = await main_agent_strategy(
            user_id=user_id,
            session_id=session_id,
            session_task_id=session_task_id,
            memories=mem,
            tools=tools,
            tool_call_function=tool_call_function,
            service_name=llm_service,
            streaming_processor=streaming_processor,
            cancel_event=cancel_event,
        )

        # 写入AI短期记忆

        ## 写入user短期记忆
        new_user_mem_first_seq_index = await get_next_seq_index(session_id)
        new_user_mem_create = [
            _UserShortTermMemoryCreate(
                user_id=user_id,
                session_id=session_id,
                content=dict(ChatCompletionUserMessageParam(
                    content=msg.content,
                    role="user",
                )),
                seq_index=new_user_mem_first_seq_index + i,
                session_task_id=session_task_id,
            ) for i, msg in enumerate(pending_messages)
        ]
        await create_user_short_term_memories_from_list(new_user_mem_create)

        ## 写入agent短期记忆
        await create_agent_short_term_memories_from_list(new_agent_memories_create)

        # 写入消息历史
        await insert_agent_messages_from_list(new_agent_messages_create)

        # 尝试压缩模型记忆
        await try_compress_short_term_memory()

        await streaming_processor.push_ending_message()
        # 更新任务状态和消息状态

        ## 更新任务状态
        await update_task_status(
            session_task_id,
            "completed",
        )
        ## 更新消息状态
        await update_user_message_status_by_ids(
            [msg.id for msg in pending_messages],
            "completed",
        )

    except Exception as e:
        await streaming_processor.push_exception_ending_message(e)
        # 更新任务状态和消息状态
        # 更新任务状态
        await update_task_status(
            session_task_id,
            "failed",
        )
        # 更新消息状态
        await update_user_message_status_by_ids(
            [msg.id for msg in pending_messages],
            "error",
        )
        # 回滚其他数据库的数据
        ## 删除用户短期记忆
        await delete_user_short_term_memories_by_session_task(session_task_id)
        ## 删除AI短期记忆
        await delete_agent_short_term_memories_by_session_task(session_task_id)
        ## 删除AI消息
        await delete_agent_messages_by_session_task(session_task_id)

    finally:
        ## 终止等待中断信号的任务
        if not wait_cancel_task.done():
            wait_cancel_task.cancel()
