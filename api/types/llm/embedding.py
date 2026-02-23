"""Embedding 数据结构 - 参考 OpenAI API"""

from typing import TypedDict, Literal
from pydantic import BaseModel
from .usage import CompletionUsageDict, CompletionUsage


# ==================== Embedding ====================

class EmbeddingDict(TypedDict):
    """嵌入向量 - TypedDict 版本（用于网络调用）"""
    index: int
    object: Literal["embedding"]
    embedding: list[float]


class Embedding(BaseModel):
    """嵌入向量 - BaseModel 版本（用于内部使用）"""
    index: int
    object: Literal["embedding"] = "embedding"
    embedding: list[float]


# ==================== Create Embedding Response ====================

class CreateEmbeddingResponseDict(TypedDict):
    """创建嵌入响应 - TypedDict 版本（用于网络调用）"""
    object: Literal["list"]
    data: list['EmbeddingDict']
    model: str
    usage: 'CompletionUsageDict'


class CreateEmbeddingResponse(BaseModel):
    """创建嵌入响应 - BaseModel 版本（用于内部使用）"""
    object: Literal["list"] = "list"
    data: list['Embedding']
    model: str
    usage: 'CompletionUsage'
