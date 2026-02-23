"""Chat 消息数据结构 - 参考 OpenAI API"""

from typing import Literal, TypedDict, NotRequired
from pydantic import BaseModel, Field
from .tool_calls import ChatCompletionMessageToolCallDict, ChatCompletionMessageToolCall


# ==================== User Message ====================

class ChatCompletionUserMessageParamDict(TypedDict):
    """用户消息参数 - TypedDict 版本（用于网络调用）"""
    role: Literal["user"]
    content: str
    name: NotRequired[str]


class ChatCompletionUserMessageParam(BaseModel):
    """用户消息参数 - BaseModel 版本（用于内部使用）"""
    role: Literal["user"] = "user"
    content: str
    name: str | None = None


# ==================== Assistant Message ====================

class ChatCompletionAssistantMessageParamDict(TypedDict):
    """助手消息参数 - TypedDict 版本（用于网络调用）"""
    role: Literal["assistant"]
    content: NotRequired[str | None]
    name: NotRequired[str]
    tool_calls: NotRequired[list[ChatCompletionMessageToolCallDict]]
    reasoning_content: NotRequired[str | None]


class ChatCompletionAssistantMessageParam(BaseModel):
    """助手消息参数 - BaseModel 版本（用于内部使用）"""
    role: Literal["assistant"] = "assistant"
    content: str | None = None
    name: str | None = None
    tool_calls: list[ChatCompletionMessageToolCall] | None = None
    reasoning_content: str | None = None


# ==================== System Message ====================

class ChatCompletionSystemMessageParamDict(TypedDict):
    """系统消息参数 - TypedDict 版本（用于网络调用）"""
    role: Literal["system"]
    content: str
    name: NotRequired[str]


class ChatCompletionSystemMessageParam(BaseModel):
    """系统消息参数 - BaseModel 版本（用于内部使用）"""
    role: Literal["system"] = "system"
    content: str
    name: str | None = None


# ==================== Tool Message ====================

class ChatCompletionToolMessageParamDict(TypedDict):
    """工具消息参数 - TypedDict 版本（用于网络调用）"""
    role: Literal["tool"]
    content: str
    tool_call_id: str


class ChatCompletionToolMessageParam(BaseModel):
    """工具消息参数 - BaseModel 版本（用于内部使用）"""
    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str


# ==================== Union Type ====================

# 用于网络调用的联合类型
ChatCompletionMessageParamDict = (
    ChatCompletionUserMessageParamDict
    | ChatCompletionAssistantMessageParamDict
    | ChatCompletionSystemMessageParamDict
    | ChatCompletionToolMessageParamDict
)

# 用于内部使用的联合类型
ChatCompletionMessageParam = (
    ChatCompletionUserMessageParam
    | ChatCompletionAssistantMessageParam
    | ChatCompletionSystemMessageParam
    | ChatCompletionToolMessageParam
)
