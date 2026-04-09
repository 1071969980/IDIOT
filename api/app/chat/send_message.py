from typing import Annotated
from fastapi import Depends, HTTPException, status

from api.authentication.utils import _User, get_current_active_user

from .router_declare import router
from .data_model import SendMessageRequest, SendMessageResponse
from api.chat.sql_stat.u2a_session.utils import (
    get_session,
    insert_session,
    _U2ASessionCreate,
)
from api.chat.sql_stat.u2a_session_branch_task.operations import get_or_create_pending_task
from api.chat.sql_stat.u2a_user_msg.utils import (
    insert_user_message,
    _U2AUserMessageCreate,
    get_next_user_message_seq_index,
)


@router.post("/send_message", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> SendMessageResponse:
    """
    发送消息到指定会话，如果未指定会话则创建新会话。
    消息会立即关联到对应分支的 pending 任务。
    该接口不调用语言模型进行实际的响应。
    """
    try:
        created_new_session = False
        session_id = request.session_id

        # 如果没有指定会话ID，则创建新会话
        if not session_id:
            session_data = _U2ASessionCreate(
                user_id=current_user.id,
                title=f"未命名的会话"
            )
            session_id = await insert_session(session_data)
            created_new_session = True
        else:
            # 验证会话是否存在且属于当前用户
            session = await get_session(session_id)
            session_exists = session is not None
            session_matches_user = session_exists and session.user_id == current_user.id

            if not session_exists or not session_matches_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="会话不存在或不属于当前用户",
                )

        # 获取或创建该分支上的 pending 任务
        task_id, _is_new = await get_or_create_pending_task(
            session_id=session_id,
            user_id=current_user.id,
            branch_name=request.branch_name,
        )

        # 获取下一条消息的序列索引
        seq_index = await get_next_user_message_seq_index(session_id)

        # 创建消息数据，直接绑定到 task
        message_data = _U2AUserMessageCreate(
            user_id=current_user.id,
            session_id=session_id,
            seq_index=seq_index,
            message_type="text",
            content=request.message,
            status="waiting_agent_ack_user",
            session_task_id=task_id,
        )

        # 插入消息
        message_id = await insert_user_message(message_data)

        return SendMessageResponse(
            session_uuid=session_id,
            message_uuid=message_id,
            message_status="waiting_agent_ack_user",
            session_task_id=task_id,
            created_new_session=created_new_session,
            message="消息发送成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发送消息失败: {e!s}",
        ) from e
