"""Completion Usage 数据结构 - 参考 OpenAI API"""

from typing import TypedDict
from pydantic import BaseModel


# ==================== Completion Usage ====================

class CompletionUsageDict(TypedDict):
    """完成使用统计 - TypedDict 版本（用于网络调用）"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class CompletionUsage(BaseModel):
    """完成使用统计 - BaseModel 版本（用于内部使用）"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
