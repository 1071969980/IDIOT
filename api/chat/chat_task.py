from asyncio import Event
from .sql_stat.u2a_session_task.utils import _U2ASessionTask
from .sql_stat.u2a_user_msg.utils import _U2AUserMessage, update_user_message_session_task_by_uuids, update_user_message_status_by_uuids
from .streaming_processor import StreamingProcessor
from api.redis.pubsub import subscribe_to_event


async def handel_processing_session_task():
    pass

async def try_compress_short_term_memory():
    pass

async def session_chat_task(
        session_id: str,
        session_task_id: str,
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
    # 更新消息状态

    ## 将所有待处理消息的所属任务更新
    await update_user_message_session_task_by_uuids(
        [msg.message_uuid for msg in pending_messages],
        session_task_id,
    )

    ## 将所有待处理消息标记为"处理中"
    update_success = await update_user_message_status_by_uuids(
        [msg.message_uuid for msg in pending_messages],
        "agent_working_for_user",
    )

    # 注册Redis取消信号的监听
    cancel_event = Event()
    redis_cancel_channel = f"session_task_canceling:{session_task_id}"
    subscribe_to_event(redis_cancel_channel, cancel_event)

    # 检查是否有正在运行的任务，并处理，可能涉及到更改先前的消息记录和追加pending_messages
    await handel_processing_session_task()

    # 尝试压缩模型记忆
    await try_compress_short_term_memory()

    # 收集AI短期记忆

    ## 构造系统提示

    ## 从数据库中构造用户和agent消息

    # 执行Agent

    # 写入AI短期记忆

    # 写入消息历史

    # 尝试压缩模型记忆
    await try_compress_short_term_memory()

    # final: 更新任务状态和消息状态