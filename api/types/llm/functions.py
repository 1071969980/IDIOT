"""Function 调用数据结构 - 参考 OpenAI API"""

from typing import Any, NotRequired, TypedDict
from pydantic import BaseModel, Field


# ==================== Function Definition ====================

class FunctionDefinitionDict(TypedDict):
    """函数定义 - TypedDict 版本（用于网络调用）"""
    name: str
    description: NotRequired[str]
    parameters: dict[str, Any]


class FunctionDefinition(BaseModel):
    """函数定义 - BaseModel 版本（用于内部使用）"""
    name: str
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


# ==================== Function Call ====================

class FunctionCallDict(TypedDict):
    """函数调用 - TypedDict 版本（用于网络调用）"""
    name: str
    arguments: str


class FunctionCall(BaseModel):
    """函数调用 - BaseModel 版本（用于内部使用）"""
    name: str
    arguments: str
