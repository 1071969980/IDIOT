import asyncio
from typing import Annotated
from uuid import UUID

import ujson
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from api.authentication.utils import _User, get_current_active_user
from api.chat.chat_task import session_chat_task
from api.chat.sql_stat.u2a_session.utils import (
    get_session,
    get_sessions_by_user_id,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    _U2ASessionTaskCreate,
    get_tasks_by_session_and_status,
    insert_task,
)
from api.chat.sql_stat.u2a_user_msg.utils import (
    get_user_messages_by_session,
    update_user_message_session_task_by_ids,
    update_user_message_status_by_ids,
)
from api.chat.stream_listener import u2a_msg_stream_generator
from api.load_balance.constant import (
    DEEPSEEK_REASONER_SERVICE_NAME,
    DEEPSEEK_CHAT_SERVICE_NAME
)

from .data_model import (
    ProcessPendingMessagesRequest,
    ProcessPendingMessagesResponse,
)
from .router_declare import router
from api.redis.distributed_lock import RedisDistributedLock

async def create_session_task_record(
        session_id: UUID,
        user_id: UUID,
):
    """
    创建一个处理会话的异步任务。
    """
    _create_task = _U2ASessionTaskCreate(
        session_id=session_id,
        user_id=user_id,
        status="processing",
    )
    return await insert_task(_create_task)

async def collect_pending_messages(
        session_id: UUID,
):
    """
    收集所有会话中的待回复消息。
    """
    all_messages = await get_user_messages_by_session(session_id)
    return [
        msg for msg in all_messages
        if msg.status == "waiting_agent_ack_user"
    ]

@router.post("/process_pending_messages", response_model=ProcessPendingMessagesResponse)
async def process_pending_messages(
    request: ProcessPendingMessagesRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> ProcessPendingMessagesResponse:
    """
    处理指定会话中还未被AI回复的消息。

    该接口会查找指定会话中状态为 'waiting_agent_ack_user' 的消息，
    将它们的状态更新为 'agent_working_for_user' 并返回处理结果。

    Args:
        request: 包含会话ID的请求对象
        current_user: 当前认证用户
        auth_header: 认证头部

    Returns:
        ProcessPendingMessagesResponse: 包含已处理消息列表的响应对象
    """
    try:
        # 1. 输入验证
        # if not request.session_id or not request.session_id.strip():
        #     raise HTTPException(
        #         status_code=status.HTTP_400_BAD_REQUEST,
        #         detail="会话ID不能为空",
        #     )

        async with RedisDistributedLock(key=f"process_pending_messages:pre_process:{request.session_id}"):
            # 2. 会话存在性验证和所有权验证
            session = await get_session(request.session_id)
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="会话不存在",
                )
            session_matches_user = session.user_id == current_user.id

            if not session_matches_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="会话不属于当前用户",
                )
            
            # 3. 检查当前会话是否存在正在运行的任务。
            during_processing_tasks = await get_tasks_by_session_and_status(
                request.session_id,
                "processing",
            )
            if during_processing_tasks:
                raise HTTPException(
                                    status_code=status.HTTP_409_CONFLICT,
                                    detail="当前会话有正在处理的任务",
                                    )

            # 4. 预检查：查询是否有待处理消息
            pending_messages = await collect_pending_messages(request.session_id)

            if not pending_messages:
                raise HTTPException(
                    status_code=status.HTTP_204_NO_CONTENT,
                    detail="没有待处理的消息",
                )
            
            # 5. 业务逻辑实现

            ## 创建任务记录到postgres
            task_uuid = await create_session_task_record(
                session_id=session.id,
                user_id=current_user.id,
            )

            ## 更新消息状态

            ## 将所有待处理消息的所属任务更新
            await update_user_message_session_task_by_ids(
                [msg.id for msg in pending_messages],
                task_uuid,
            )

            ## 将所有待处理消息标记为"处理中"
            await update_user_message_status_by_ids(
                [msg.id for msg in pending_messages],
                "agent_working_for_user",
            )
        
        # 发起后台任务
        asyncio.create_task(session_chat_task( # type: ignore # noqa: RUF006
            user_id=current_user.id,
            session_id=session.id,
            session_task_id=task_uuid,
            llm_service=DEEPSEEK_CHAT_SERVICE_NAME,
            pending_messages=pending_messages,
            during_processing_tasks=during_processing_tasks,
        )) 

        # 返回SSE响应流
        return ProcessPendingMessagesResponse(
            session_id=session.id,
            session_task_id=task_uuid,
            processed_messages_id=[msg.id for msg in pending_messages],
            total_processed=len(pending_messages)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理未回复消息时发生错误: {e!s}",
        ) from e
