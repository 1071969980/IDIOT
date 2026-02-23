"""Tool 调用数据结构 - 参考 OpenAI API"""

from typing import Literal, TypedDict, NotRequired
from pydantic import BaseModel, Field
from .functions import FunctionCallDict, FunctionCall, FunctionDefinitionDict, FunctionDefinition


# ==================== Chat Completion Tool Param ====================

class ChatCompletionToolParamDict(TypedDict):
    """工具参数 - TypedDict 版本（用于网络调用）"""
    type: Literal["function"]
    function: FunctionDefinitionDict


class ChatCompletionToolParam(BaseModel):
    """工具参数 - BaseModel 版本（用于内部使用）"""
    type: Literal["function"] = "function"
    function: FunctionDefinition


# ==================== Chat Completion Message Tool Call ====================

class ChatCompletionMessageToolCallDict(TypedDict):
    """消息中的工具调用 - TypedDict 版本（用于网络调用）"""
    id: str
    type: Literal["function"]
    function: FunctionCallDict


class ChatCompletionMessageToolCall(BaseModel):
    """消息中的工具调用 - BaseModel 版本（用于内部使用）"""
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall
