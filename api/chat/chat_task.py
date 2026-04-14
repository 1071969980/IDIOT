import asyncio
import traceback
from asyncio import Event
from typing import TYPE_CHECKING
from uuid import UUID

import logfire
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

from api.agent.strategy.main_agent_strategy import main_agent_strategy
from api.agent.tools.mcp.adapter import McpToolsLoader
from api.agent.tools.type import ToolClosure
from api.chat.data_model import ToolInitializationResult
from api.human_in_loop.context import HILMessageStreamContext
from api.logger.datamodel import LangFuseSpanAttributes, LangFuseTraceAttributes
from api.logger.exception_dump import save_exception_stack_async
from api.redis.redis_event import subscribe_to_event

if TYPE_CHECKING:
    from api.chat.tool_init import _EmptyAsyncContextManager
    

from .exception import SessionChatTaskCancelled
from .sql_stat.u2a_agent_msg.utils import (
    delete_agent_messages_by_session_task,
    insert_agent_messages_from_list,
)
from .sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryResponse,
    create_agent_short_term_memories_from_list,
    delete_agent_short_term_memories_by_session_task,
)
from .sql_stat.u2a_session_task.utils import (
    _U2ASessionTask,
    update_task_status,
)
from .sql_stat.u2a_user_msg.utils import (
    _U2AUserMessage,
    update_user_message_status_by_ids,
)
from .sql_stat.u2a_user_short_term_memory.utils import (
    _UserShortTermMemoryCreate,
    _UserShortTermMemoryResponse,
    create_user_short_term_memories_from_list,
    delete_user_short_term_memories_by_session_task,
    get_next_seq_index,
)
from .streaming_processor import StreamingProcessor


async def handel_processing_session_task(tasks: list[_U2ASessionTask]):
    pass

async def try_compress_short_term_memory():
    pass

async def query_short_term_memory(
    session_task_id: UUID,
) -> list[dict]:
    from .sql_stat.u2a_agent_short_term_memory.utils import (
        get_memories_by_session_task_ids as get_agent_memories,
    )
    from .sql_stat.u2a_session_task.utils import (
        get_tasks_on_branch_path_until_breakpoint,
    )
    from .sql_stat.u2a_user_short_term_memory.utils import (
        get_memories_by_session_task_ids as get_user_memories,
    )

    # --- 排序策略说明 ---
    # 最终顺序由两层排序决定：
    #   外层: task 按 seq_in_session ASC（即创建时间顺序：断点 → ... → leaf）
    #   内层: 每个 task 内的记忆按各自的 seq 索引排序
    # SQL 返回的记忆虽然也有 ORDER BY session_task_id, seq_index/sub_seq_index，
    # 但 session_task_id 按 UUID 排序并不保证与 seq_in_session 一致，
    # 因此用 dict 分组后再按 task_path 顺序遍历，确保最终拼接正确。

    # 1. 获取 task 路径（SQL: ORDER BY seq_in_session ASC）
    task_path = await get_tasks_on_branch_path_until_breakpoint(session_task_id)
    if not task_path:
        return []

    task_ids = [task.id for task in task_path]

    # 2. 批量查询记忆
    # user 记忆:   SQL ORDER BY session_task_id, seq_index（同 task 内按 seq_index 排序）
    # agent 记忆:  SQL ORDER BY session_task_id, sub_seq_index（同 task 内按 sub_seq_index 排序）
    user_memories = await get_user_memories(task_ids)
    agent_memories = await get_agent_memories(task_ids)

    # 3. 按 session_task_id 分组，保留 SQL 的同 task 内排序
    grouped_user: dict[UUID, list[_UserShortTermMemoryResponse]] = {}
    for mem in user_memories:
        grouped_user.setdefault(mem.session_task_id, []).append(mem)

    grouped_agent: dict[UUID, list[_AgentShortTermMemoryResponse]] = {}
    for mem in agent_memories:
        grouped_agent.setdefault(mem.session_task_id, []).append(mem)

    # 4. 按 task_path 顺序（seq_in_session ASC）遍历，拼接记忆
    merged_memories: list[dict] = []

    for task in task_path:
        # user 记忆
        if task.id in grouped_user:
            if task.context_breakpoints:
                pass # 跳过该 task 的所有 user 记忆
            else:
                merged_memories.extend(mem.content for mem in grouped_user[task.id])

        # agent 记忆（含 context_breakpoints 截断逻辑）
        if task.id in grouped_agent:
            agent_mems = grouped_agent[task.id]
            if task.context_breakpoints:
                last_bp = task.context_breakpoints[-1]
                if last_bp == -1:
                    pass  # 跳过该 task 的所有 agent 记忆
                else:
                    merged_memories.extend(
                        mem.content for mem in agent_mems if mem.sub_seq_index >= last_bp
                    )
            else:
                merged_memories.extend(mem.content for mem in agent_mems)

    return merged_memories

async def session_chat_task(
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        llm_service: str,
        system_prompt: str,
        pending_messages: list[_U2AUserMessage],
        during_processing_tasks: list[_U2ASessionTask],
        tool_init_res: ToolInitializationResult,
        mcp_tools_loader: _EmptyAsyncContextManager | McpToolsLoader,
        cancel_event: Event | None = None,
) -> Exception | None:
    langfuse_trace_attributes = LangFuseTraceAttributes(
        name="api/chat/chat_task.py::session_chat_task",
        user_id=str(user_id),
        session_id=str(session_id),
        metadata={
            "session_task_id": str(session_task_id),
        },
    ) # type: ignore

    with logfire.set_baggage(**langfuse_trace_attributes.model_dump(mode="json", by_alias=True)) as _:
        langfuse_observation_attributes = LangFuseSpanAttributes(
            observation_type="span",
        ) # type: ignore
        with logfire.span("api/chat/chat_task.py::session_chat_task",
                          **langfuse_observation_attributes.model_dump(mode="json", by_alias=True)) as span:
            return await __session_chat_task(
                user_id=user_id,
                session_id=session_id,
                session_task_id=session_task_id,
                llm_service=llm_service,
                system_prompt=system_prompt,
                pending_messages=pending_messages,
                during_processing_tasks=during_processing_tasks,
                tool_init_res=tool_init_res,
                mcp_tools_loader=mcp_tools_loader,
                cancel_event=cancel_event,
            )

async def __session_chat_task(
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        llm_service: str,
        system_prompt: str,
        pending_messages: list[_U2AUserMessage],
        during_processing_tasks: list[_U2ASessionTask],
        tool_init_res: ToolInitializationResult,
        mcp_tools_loader: _EmptyAsyncContextManager | McpToolsLoader,
        cancel_event: Event | None = None,
):
    ret_exception = None
    wait_cancel_task: asyncio.Task[None] | None = None  # 初始化以避免 unbound 错误

    # 初始化处理管道
    streaming_processor = StreamingProcessor(
        task_uuid=session_task_id,
    )

    HIL_stream_context = HILMessageStreamContext(
        stream_identifier=str(session_task_id),
    )

    async with streaming_processor, HIL_stream_context, mcp_tools_loader:
        """
        处理所有会话中的待回复消息。
        """
        # 加载 MCP 工具到 tools 和 tool_call_function
        # if mcp_tools_loader:
        #     mcp_tools, mcp_tool_call_function = mcp_tools_loader.get_tools()
        #     tools.extend(mcp_tools)
        #     tool_call_function.update(mcp_tool_call_function)

        try:
            # 注册Redis取消信号的监听
            if cancel_event is None:
                cancel_event = Event()
                redis_cancel_channel = f"session_task_canceling:{session_task_id}"
                wait_cancel_task = asyncio.create_task(
                    subscribe_to_event(redis_cancel_channel, cancel_event),
                )

            # 将 mcp 工具合并进 tool_init_res
            if isinstance(mcp_tools_loader, McpToolsLoader):
                mcp_tools = mcp_tools_loader.get_tools()
                tool_init_res.merge_inplace(mcp_tools)

            # 检查是否有正在运行的任务，并处理，可能涉及到更改先前的消息记录和追加pending_messages
            await handel_processing_session_task(during_processing_tasks)

            # 尝试压缩模型记忆
            await try_compress_short_term_memory()

            # 收集AI短期记忆
            ## 构造系统提示
            sys_mem = ChatCompletionSystemMessageParam(
                content=system_prompt,
                role="system",
            )

            ## 从数据库中构造用户和agent短期记忆
            user_and_agent_memories_json = await query_short_term_memory(session_task_id=session_task_id)

            pending_messages_sorted = pending_messages.copy()
            pending_messages_sorted.sort(key=lambda x: x.process_priority)

            ## 添加当次任务的user消息
            new_user_mem = [
                ChatCompletionUserMessageParam(
                    content=msg.content,
                    role="user",
                )
                for msg in pending_messages_sorted
            ]
            
            ## 合并这些记忆
            mem = []
            mem.append(sys_mem)
            mem.extend(user_and_agent_memories_json)
            mem.extend(new_user_mem)

            # 执行Agent
            new_agent_memories_create, new_agent_messages_create = await main_agent_strategy(
                user_id=user_id,
                session_id=session_id,
                session_task_id=session_task_id,
                memories=mem,
                tool_init_res=tool_init_res,
                service_name=llm_service,
                streaming_processor=streaming_processor,
                cancel_event=cancel_event,
            )

            await streaming_processor.push_ending_message()

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
                ) for i, msg in enumerate(pending_messages_sorted)
            ]

            await create_user_short_term_memories_from_list(new_user_mem_create)

            ## 写入agent短期记忆
            await create_agent_short_term_memories_from_list(new_agent_memories_create)

            # 写入消息历史
            await insert_agent_messages_from_list(new_agent_messages_create)

            # 尝试压缩模型记忆
            await try_compress_short_term_memory()

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

        except SessionChatTaskCancelled as e:
            #  处理取消,
            # !!! 目前，可以断言在取消发生时，Agent必定正在执行，并且处于生成文本的阶段。

            await streaming_processor.push_exception_ending_message(e)

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
                ) for i, msg in enumerate(pending_messages_sorted)
            ]
            await create_user_short_term_memories_from_list(new_user_mem_create)

            ## 写入agent短期记忆
            await create_agent_short_term_memories_from_list(e.new_agent_memory)

            # 写入消息历史
            await insert_agent_messages_from_list(e.new_agent_message)

            # 更新任务状态和消息状态
            # 更新任务状态
            await update_task_status(
                session_task_id,
                "cancelled",
            )
            # 更新消息状态
            await update_user_message_status_by_ids(
                [msg.id for msg in pending_messages],
                "completed",
            )

        except Exception as e:
            # unhandled exception
            logfire.error("api/chat/chat_task.py::session_chat_task#unhandled_exception",
                          traceback=traceback.format_exc())
            await streaming_processor.push_exception_ending_message(e)
            save_exception_stack_async(e, f"session_chat_task_{session_task_id}")
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

            ret_exception = e
        finally:
            ## 终止等待中断信号的任务
            if wait_cancel_task is not None and not wait_cancel_task.done():
                wait_cancel_task.cancel()

    return ret_exception
