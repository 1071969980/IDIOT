from typing import Literal
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime 
from api.chat.sql_stat.u2a_agent_msg.utils import (
    _U2AAgentMessage,
)
from api.chat.sql_stat.u2a_user_msg.utils import (
    _U2AUserMessage,
)

class SessionResponse(BaseModel):
    """会话响应模型"""
    id: UUID
    user_id: UUID
    title: str
    archived: bool
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    """会话列表响应模型"""
    sessions: list[SessionResponse]


class CreateSessionRequest(BaseModel):
    """创建会话请求模型"""
    title: str | None = Field(default="", description="会话标题")


class UpdateSessionTitleRequest(BaseModel):
    """更新会话标题请求模型"""
    session_id: UUID = Field(..., description="会话ID")
    title: str = Field(..., description="新的会话标题")

class SessionMessageHistoryRequest(BaseModel):
    """获取会话消息历史请求模型"""
    session_id: UUID = Field(..., description="会话ID")
    limit: int | None = Field(None, description="返回消息数量限制")
    max_seq_index: int | None = Field(None, description="最大序号限制")

class SessionMessageHistoryResponseItem(BaseModel):
    role: Literal["user", "assistant"]
    message: _U2AAgentMessage | _U2AUserMessage

class SessionMessageHistoryResponse(BaseModel):
    """获取会话消息历史响应模型"""
    session_id: UUID
    messages: list[SessionMessageHistoryResponseItem]


class SendMessageRequest(BaseModel):
    """发送消息请求模型"""
    message: str = Field(..., description="消息内容", min_length=1)
    session_id: UUID | None = Field(None, description="会话ID，如果为空则创建新会话")


class SendMessageResponse(BaseModel):
    """发送消息响应模型"""
    session_uuid: UUID
    message_uuid: UUID
    created_new_session: bool
    message: str = "消息发送成功"


class ProcessPendingMessagesRequest(BaseModel):
    """处理未回复消息请求模型"""
    session_id: UUID = Field(..., description="会话ID")

class ProcessPendingMessagesResponse(BaseModel):
    """处理未回复消息响应模型"""
    session_id: UUID
    session_task_id: UUID
    processed_messages_id: list[UUID]
    total_processed: int
    message: str = "未回复消息处理完成"

class ChatStreamingRequset(BaseModel):
    """会话流式请求模型"""
    session_id: UUID = Field(..., description="会话ID")
    session_task_id: UUID = Field(..., description="会话任务ID")