from fastapi import APIRouter, HTTPException
from typing import List
import logfire
from openai import NOT_GIVEN

from .data_model import (
    VectorObjectCreate, 
    VectorObjectResponse, 
    VectorSearchRequest, 
    TextSearchRequest,
    DeleteByIdsRequest,
    DeleteByMetadataRequest
)
from api.vector_db.weaviate.simple_text.simple_text_sync import SimpleTextVectorDB_Weaviate, SimpleTextObeject_Weaviate
from api.vector_db.weaviate.simple_text.simple_text_def import SIMPLE_TEXT_OBEJECT_SCHEMA
from api.vector_db.weaviate.init_impl import create_collection_or_tenant
from api.load_balance.constant import LOAD_BLANCER, QWEN_TEXT_EMBEDDING_SERVICE_NAME
from api.load_balance.delegate.openai import embedding_delegate_for_async_openai

__all__ = ["router"]

router = APIRouter(
    prefix="/simple_text_vector_db",
    tags=["simple_text_vector_db"],
)

@router.post("/init", response_model=dict)
async def init_vector_db(collection_name: str = "default_collection",
                          tenant_name: str | None = "default_tenant"):
    await create_collection_or_tenant(collection_name, tenant_name, SIMPLE_TEXT_OBEJECT_SCHEMA)
    msg_1 = f"collection {collection_name} created successfully"
    msg_2 = f"tenant {tenant_name} created successfully"
    msg = f"{msg_1}. {msg_2}" if tenant_name else msg_1
    return {"status": "success", "message": msg}


@router.post("/objects", response_model=dict)
async def create_vector_object(obj: VectorObjectCreate):
    """
    创建单个向量对象
    """
    try:
        # 如果没有提供向量，则使用通义千问嵌入服务生成向量
        vector = obj.vector
        if vector is None:
            vector = await _generate_embedding(obj.text)
        
        vector_db = SimpleTextVectorDB_Weaviate(
            collection_name=obj.collection_name or "default_collection",
            tenant_name=obj.tenant_name or "default_tenant"
        )
        
        vector_obj = SimpleTextObeject_Weaviate(
            text=obj.text,
            collection_name=obj.collection_name,
            tenant_name=obj.tenant_name,
            vector=vector
        )
        
        vector_db.add_object(vector_obj)
        return {"status": "success", "message": "Object created successfully"}
    except Exception as e:
        logfire.error("Failed to create vector object: {error}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create vector object: {str(e)}")


@router.post("/objects/batch", response_model=dict)
async def create_vector_objects(objs: List[VectorObjectCreate]):
    """
    批量创建向量对象
    """
    try:
        if not objs:
            raise HTTPException(status_code=400, detail="No objects provided")
            
        # 检查所有对象是否具有相同的collection_name和tenant_name
        first_obj = objs[0]
        collection_name = first_obj.collection_name or "default_collection"
        tenant_name = first_obj.tenant_name or "default_tenant"
        
        for obj in objs:
            if (obj.collection_name or "default_collection") != collection_name:
                raise HTTPException(status_code=400, detail="All objects must have the same collection name")
            if (obj.tenant_name or "default_tenant") != tenant_name:
                raise HTTPException(status_code=400, detail="All objects must have the same tenant name")
        
        vector_db = SimpleTextVectorDB_Weaviate(
            collection_name=collection_name,
            tenant_name=tenant_name
        )
        
        vector_objs = []
        for obj in objs:
            # 如果没有提供向量，则使用通义千问嵌入服务生成向量
            vector = obj.vector
            if vector is None:
                vector = await _generate_embedding(obj.text)
                
            vector_obj = SimpleTextObeject_Weaviate(
                text=obj.text,
                collection_name=obj.collection_name,
                tenant_name=obj.tenant_name,
                vector=vector
            )
            vector_objs.append(vector_obj)
        
        vector_db.add_objects(vector_objs)
        return {"status": "success", "message": f"Successfully created {len(objs)} objects"}
    except Exception as e:
        logfire.error("Failed to create vector objects: {error}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create vector objects: {str(e)}")


@router.get("/objects/{obj_id}/exists", response_model=dict)
async def check_object_exists(obj_id: str, collection_name: str = "default_collection", tenant_name: str = "default_tenant"):
    """
    检查对象ID是否存在
    """
    try:
        vector_db = SimpleTextVectorDB_Weaviate(
            collection_name=collection_name,
            tenant_name=tenant_name
        )
        
        exists = vector_db.id_exists(obj_id)
        return {"id": obj_id, "exists": exists}
    except Exception as e:
        logfire.error("Failed to check object existence: {error}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to check object existence: {str(e)}")


@router.post("/search/vector", response_model=List[VectorObjectResponse])
async def search_by_vector(request: VectorSearchRequest, collection_name: str = "default_collection", tenant_name: str = "default_tenant"):
    """
    根据向量搜索相似对象
    """
    try:
        vector_db = SimpleTextVectorDB_Weaviate(
            collection_name=collection_name,
            tenant_name=tenant_name
        )
        
        kwargs = {}
        if request.limit:
            kwargs["limit"] = request.limit
        if request.certainty:
            kwargs["certainty"] = request.certainty
            
        results = vector_db.search_by_vector(request.query_vector, **kwargs)
        
        response = [
            VectorObjectResponse(
                text=result.text,
                collection_name=result.collection_name,
                tenant_name=result.tenant_name,
                vector=result.vector.tolist() if hasattr(result.vector, 'tolist') else result.vector
            ) for result in results
        ]
        
        return response
    except Exception as e:
        logfire.error("Failed to search by vector: {error}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to search by vector: {str(e)}")


@router.post("/search/text", response_model=List[VectorObjectResponse])
async def search_by_text(request: TextSearchRequest, collection_name: str = "default_collection", tenant_name: str = "default_tenant"):
    """
    根据文本搜索对象（关键词搜索）
    """
    try:
        vector_db = SimpleTextVectorDB_Weaviate(
            collection_name=collection_name,
            tenant_name=tenant_name
        )
        
        kwargs = {}
        if request.limit:
            kwargs["limit"] = request.limit
            
        results = vector_db.search_by_text(request.query, **kwargs)
        
        response = [
            VectorObjectResponse(
                text=result.text,
                collection_name=result.collection_name,
                tenant_name=result.tenant_name,
                vector=result.vector.tolist() if hasattr(result.vector, 'tolist') else result.vector
            ) for result in results
        ]
        
        return response
    except Exception as e:
        logfire.error("Failed to search by text: {error}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to search by text: {str(e)}")


@router.delete("/objects", response_model=dict)
async def delete_objects_by_ids(request: DeleteByIdsRequest, collection_name: str = "default_collection", tenant_name: str = "default_tenant"):
    """
    根据IDs删除对象
    """
    try:
        if not request.ids:
            raise HTTPException(status_code=400, detail="No IDs provided")
            
        vector_db = SimpleTextVectorDB_Weaviate(
            collection_name=collection_name,
            tenant_name=tenant_name
        )
        
        vector_db.delete_by_ids(request.ids)
        return {"status": "success", "message": f"Deleted {len(request.ids)} objects"}
    except Exception as e:
        logfire.error("Failed to delete objects by IDs: {error}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete objects by IDs: {str(e)}")


@router.delete("/objects/metadata", response_model=dict)
async def delete_objects_by_metadata(request: DeleteByMetadataRequest, collection_name: str = "default_collection", tenant_name: str = "default_tenant"):
    """
    根据元数据字段删除对象
    """
    try:
        vector_db = SimpleTextVectorDB_Weaviate(
            collection_name=collection_name,
            tenant_name=tenant_name
        )
        
        vector_db.delete_by_metadata_field(request.key, request.value)
        return {"status": "success", "message": f"Deleted objects with {request.key}={request.value}"}
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Delete by metadata not implemented")
    except Exception as e:
        logfire.error("Failed to delete objects by metadata: {error}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete objects by metadata: {str(e)}")


async def _generate_embedding(text: str) -> List[float]:
    """
    使用通义千问嵌入服务生成文本的向量表示
    """
    async def _embed_request(service_instance):
        return (await embedding_delegate_for_async_openai(
            service_instance=service_instance,
            text=text,
        )).data
    
    try:
        embeddings = await LOAD_BLANCER.execute(
            QWEN_TEXT_EMBEDDING_SERVICE_NAME,
            _embed_request
        )
        return embeddings[0].embedding
    except Exception as e:
        logfire.error("Failed to generate embedding: {error}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate embedding: {str(e)}")