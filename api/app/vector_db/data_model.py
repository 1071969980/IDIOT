
from pydantic import BaseModel


class VectorObjectCreate(BaseModel):
    """
    创建向量对象的数据模型
    """
    text: str
    collection_name: str | None = None
    tenant_name: str | None = None
    vector: list[float] | None = None


class VectorObjectUpdate(BaseModel):
    """
    更新向量对象的数据模型
    """
    text: str | None = None
    vector: list[float] | None = None


class VectorObjectResponse(BaseModel):
    """
    向量对象响应的数据模型
    """
    text: str
    collection_name: str | None
    tenant_name: str | None
    vector: list[float] | None


class VectorSearchRequest(BaseModel):
    """
    向量搜索请求的数据模型
    """
    query_vector: list[float] | dict[str, list[float]]
    limit: int | None = 10
    certainty: float | None = None


class TextSearchRequest(BaseModel):
    """
    文本搜索请求的数据模型
    """
    query: str
    limit: int | None = 10


class DeleteByIdsRequest(BaseModel):
    """
    根据ID删除对象的请求数据模型
    """
    ids: list[str]


class DeleteByMetadataRequest(BaseModel):
    """
    根据元数据删除对象的请求数据模型
    """
    key: str
    value: str
