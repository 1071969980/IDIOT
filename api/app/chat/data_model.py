from pydantic import BaseModel, Field
from uuid import UUID


class SessionResponse(BaseModel):
    """会话响应模型"""
    id: UUID
    user_id: UUID
    title: str
    archived: bool
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """会话列表响应模型"""
    sessions: list[SessionResponse]


class CreateSessionRequest(BaseModel):
    """创建会话请求模型"""
    title: str | None = Field(default="", description="会话标题")


class UpdateSessionTitleRequest(BaseModel):
    """更新会话标题请求模型"""
    session_id: str = Field(..., description="会话ID")
    title: str = Field(..., description="新的会话标题")


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
    session_id: str = Field(..., description="会话ID")


class ProcessedMessageResponse(BaseModel):
    """已处理消息响应模型"""
    message_id: int
    message_uuid: str
    content: str
    role: str
    original_status: str
    new_status: str = "agent_working_for_user"


class ProcessPendingMessagesResponse(BaseModel):
    """处理未回复消息响应模型"""
    session_id: str
    processed_messages: list[ProcessedMessageResponse]
    total_processed: int
    message: str = "未回复消息处理完成"