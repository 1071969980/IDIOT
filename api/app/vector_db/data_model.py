from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union


class VectorObjectCreate(BaseModel):
    """
    创建向量对象的数据模型
    """
    text: str
    collection_name: Optional[str] = None
    tenant_name: Optional[str] = None
    vector: List[float]


class VectorObjectUpdate(BaseModel):
    """
    更新向量对象的数据模型
    """
    text: Optional[str] = None
    vector: Optional[List[float]] = None


class VectorObjectResponse(BaseModel):
    """
    向量对象响应的数据模型
    """
    text: str
    collection_name: Optional[str]
    tenant_name: Optional[str]
    vector: Optional[List[float]]


class VectorSearchRequest(BaseModel):
    """
    向量搜索请求的数据模型
    """
    query_vector: Union[List[float], Dict[str, List[float]]]
    limit: Optional[int] = 10
    certainty: Optional[float] = None


class TextSearchRequest(BaseModel):
    """
    文本搜索请求的数据模型
    """
    query: str
    limit: Optional[int] = 10


class DeleteByIdsRequest(BaseModel):
    """
    根据ID删除对象的请求数据模型
    """
    ids: List[str]


class DeleteByMetadataRequest(BaseModel):
    """
    根据元数据删除对象的请求数据模型
    """
    key: str
    value: str