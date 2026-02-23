"""流式响应数据结构 - 参考 OpenAI API"""

from typing import TypedDict, Literal, NotRequired, Any
from pydantic import BaseModel
from .functions import FunctionCallDict, FunctionCall
from .tool_calls import ChatCompletionMessageToolCallDict, ChatCompletionMessageToolCall
from .usage import CompletionUsageDict, CompletionUsage


# ==================== Choice Delta Tool Call ====================

class ChoiceDeltaToolCallFunctionDict(TypedDict):
    """工具调用函数的增量更新 - TypedDict 版本（用于网络调用）"""
    name: NotRequired[str]
    arguments: NotRequired[str]


class ChoiceDeltaToolCallFunction(BaseModel):
    """工具调用函数的增量更新 - BaseModel 版本（用于内部使用）"""
    name: str | None = None
    arguments: str | None = None


class ChoiceDeltaToolCallDict(TypedDict):
    """工具调用的增量更新 - TypedDict 版本（用于网络调用）"""
    id: NotRequired[str | None]
    index: int
    type: NotRequired[Literal["function"] | None]
    function: NotRequired[dict | None]


class ChoiceDeltaToolCall(BaseModel):
    """工具调用的增量更新 - BaseModel 版本（用于内部使用）"""
    id: str | None = None
    index: int
    type: Literal["function"] | None = None
    function: FunctionCall | None = None


# ==================== Choice Delta ====================

class ChoiceDeltaDict(TypedDict):
    """选择增量 - TypedDict 版本（用于网络调用）"""
    role: NotRequired[Literal["assistant"] | None]
    content: NotRequired[str | None]
    tool_calls: NotRequired[list[dict] | None]


class ChoiceDelta(BaseModel):
    """选择增量 - BaseModel 版本（用于内部使用）"""
    role: Literal["assistant"] | None = None
    content: str | None = None
    tool_calls: list[ChatCompletionMessageToolCall] | None = None


# ==================== Chat Completion Chunk ====================

class ChatCompletionChunkChoiceDict(TypedDict):
    """流式响应的选择 - TypedDict 版本（用于网络调用）"""
    index: int
    delta: dict
    finish_reason: NotRequired[Literal["stop", "length", "tool_calls", "content_filter"] | None]
    logprobs: NotRequired[dict | None]


class ChatCompletionChunkChoice(BaseModel):
    """流式响应的选择 - BaseModel 版本（用于内部使用）"""
    index: int
    delta: ChoiceDelta
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None = None
    logprobs: dict | None = None


class ChatCompletionChunkDict(TypedDict):
    """流式响应 - TypedDict 版本（用于网络调用）"""
    id: str
    object: Literal["chat.completion.chunk"]
    created: int
    model: str
    choices: list[dict]
    usage: NotRequired[dict | None]


class ChatCompletionChunk(BaseModel):
    """流式响应 - BaseModel 版本（用于内部使用）"""
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatCompletionChunkChoice]
    usage: CompletionUsage | None = None
