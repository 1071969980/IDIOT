"""Chat Completion 响应数据结构 - 参考 OpenAI API"""

from typing import TypedDict, Literal, NotRequired
from pydantic import BaseModel
from .tool_calls import ChatCompletionMessageToolCallDict, ChatCompletionMessageToolCall
from .usage import CompletionUsageDict, CompletionUsage


# ==================== Message ====================

class MessageDict(TypedDict):
    """完成响应中的消息 - TypedDict 版本（用于网络调用）"""
    role: Literal["assistant"]
    content: str | None
    tool_calls: NotRequired[list[ChatCompletionMessageToolCallDict] | None]


class Message(BaseModel):
    """完成响应中的消息 - BaseModel 版本（用于内部使用）"""
    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: list[ChatCompletionMessageToolCall] | None = None


# ==================== Chat Completion Choice ====================

class ChatCompletionChoiceDict(TypedDict):
    """完成响应的选择 - TypedDict 版本（用于网络调用）"""
    index: int
    message: MessageDict
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"]


class ChatCompletionChoice(BaseModel):
    """完成响应的选择 - BaseModel 版本（用于内部使用）"""
    index: int
    message: Message
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"]


# ==================== Chat Completion ====================

class ChatCompletionDict(TypedDict):
    """聊天完成响应 - TypedDict 版本（用于网络调用）"""
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: list[ChatCompletionChoiceDict]
    usage: CompletionUsageDict


class ChatCompletion(BaseModel):
    """聊天完成响应 - BaseModel 版本（用于内部使用）"""
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: CompletionUsage
