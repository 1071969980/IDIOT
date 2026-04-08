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
    title: str | None = Field(default="未命名的会话", description="会话标题")


class CreateSessionResponse(BaseModel):
    """创建会话响应模型"""
    session_uuid: UUID
    created_new_session: bool
    message: str = "会话获取成功"


class UpdateSessionTitleRequest(BaseModel):
    """更新会话标题请求模型"""
    session_id: UUID = Field(..., description="会话ID")
    title: str = Field(..., description="新的会话标题")

class SessionMessageHistoryRequest(BaseModel):
    """获取会话消息历史请求模型"""
    session_id: UUID = Field(..., description="会话ID")
    branch_name: str = Field(default="main", description="分支名称，默认为 main")
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
    branch_name: str = Field(default="main", description="分支名称，默认为 main")


class SendMessageResponse(BaseModel):
    """发送消息响应模型"""
    session_uuid: UUID
    message_uuid: UUID
    session_task_id: UUID | None = Field(None, description="关联的会话任务ID")
    created_new_session: bool
    message: str = "消息发送成功"


class ProcessPendingMessagesRequest(BaseModel):
    """处理未回复消息请求模型"""
    session_id: UUID = Field(..., description="会话ID")
    branch_name: str = Field(default="main", description="分支名称，默认为 main")

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

class CancelSessionTaskRequest(BaseModel):
    """取消会话任务请求模型"""
    session_id: UUID = Field(..., description="会话ID")
    session_task_id: UUID = Field(..., description="会话任务ID")


class ProcessingTaskInfo(BaseModel):
    """处理中任务信息模型"""
    id: UUID = Field(..., description="任务ID")
    branch_id: UUID | None = Field(None, description="所属分支ID")
    branch_name: str | None = Field(None, description="所属分支名称")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class GetProcessingTaskRequest(BaseModel):
    """获取处理中任务请求模型"""
    session_id: UUID = Field(..., description="会话ID")
    branch_name: str = Field(..., description="分支名称")


class GetProcessingTaskResponse(BaseModel):
    """获取处理中任务响应模型"""
    session_id: UUID = Field(..., description="会话ID")
    has_processing_task: bool = Field(..., description="是否有处理中任务")
    processing_tasks: list[ProcessingTaskInfo] = Field(default=[], description="处理中任务列表")
    total_count: int = Field(default=0, description="处理中任务总数")


class DeleteSessionRequest(BaseModel):
    """删除会话请求模型"""
    session_ids: list[UUID] = Field(..., description="会话ID列表", min_length=1)


class DeleteSessionResult(BaseModel):
    """单个会话删除结果"""
    session_id: UUID = Field(..., description="会话ID")
    success: bool = Field(..., description="是否删除成功")
    reason: str | None = Field(None, description="失败原因")


class DeleteSessionResponse(BaseModel):
    """批量删除会话响应模型"""
    total_requested: int = Field(..., description="请求删除的会话总数")
    deleted_count: int = Field(..., description="成功删除的会话数")
    failed_count: int = Field(..., description="删除失败的会话数")
    results: list[DeleteSessionResult] = Field(..., description="每个会话的删除结果")