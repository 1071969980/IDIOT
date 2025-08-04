from typing import Any

from weaviate.classes.query import Filter
from weaviate.collections.classes.data import DataObject
from weaviate.util import generate_uuid5

from api.vector_db.vector_db_base import AsyncBaseVectorDB
from api.vector_db.weaviate.constant import _async_client

from .simple_text_def import SimpleTextObeject_Weaviate


class AsyncSimpleTextVectorDB_Weaviate(AsyncBaseVectorDB[SimpleTextObeject_Weaviate]):
    def __init__(self, collection_name: str = "default_collection", tenant_name: str = "default_tenant"):
        self.collection_name = collection_name
        self.tenant_name = tenant_name
    async def add_object(self,
                         obj:SimpleTextObeject_Weaviate,
                         **kwargs: dict[str, Any]):
        async with _async_client() as client:
            collection_name = obj.collection_name or self.collection_name
            tenant_name = obj.tenant_name or self.tenant_name
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            await tenant.data.insert(
                properties = {
                    "text": obj.text,
                },
                vector=obj.vector,
            )

    async def add_objects(self,
                          objs: list[SimpleTextObeject_Weaviate],
                          **kwargs: dict[str, Any]):
        # assert all objs have the same collection name and tenant name
        if not all(obj.collection_name == objs[0].collection_name for obj in objs):
            raise ValueError("All objs must have the same collection name")
        if not all(obj.tenant_name == objs[0].tenant_name for obj in objs):
            raise ValueError("All objs must have the same tenant name")
        # assert all objs have the vector
        if not all(obj.vector is not None for obj in objs):
            raise ValueError("All objs must have the vector")
        collection_name = objs[0].collection_name or self.collection_name
        tenant_name = objs[0].tenant_name or self.tenant_name
        async with _async_client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            await tenant.data.insert_many(
                [
                    DataObject(
                        properties={
                            "text": obj.text,
                        },
                        vector=obj.vector,
                        uuid=generate_uuid5(collection_name + tenant_name + obj.text),
                    )
                    for obj in objs
                ],
            )

    async def id_exists(self, id: str):
        collection_name = self.collection_name
        tenant_name = self.tenant_name
        async with _async_client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            return await tenant.data.exists(id)

    async def delete_by_ids(self, ids: list[str]):
        collection_name = self.collection_name
        tenant_name = self.tenant_name
        async with _async_client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            await tenant.data.delete_many(
                where=Filter.by_id().contains_any(ids),
            )

    async def search_ids_by_metadata_field(self, key, value):
        raise NotImplementedError

    async def delete_by_metadata_field(self, key, value):
        raise NotImplementedError

    async def search_by_vector(self, query_vector, **kwargs):
        collection_name = self.collection_name
        tenant_name = self.tenant_name
        async with _async_client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            response = await tenant.query.near_vector(
                near_vector=query_vector
                **kwargs,
            )

        return [
            SimpleTextObeject_Weaviate(
                text=obj.properties["text"],
                collection_name=collection_name,
                tenant_name=tenant_name,
                vector=next(obj.vector.values()),
            )
            for obj in response.objects
        ]

    async def search_by_text(self, query, **kwargs):
        """
        keyword search by bm25
        """
        collection_name = self.collection_name
        tenant_name = self.tenant_name
        async with _async_client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            response = await tenant.query.bm25(
                query=query,
                **kwargs,
            )
        
        return [
            SimpleTextObeject_Weaviate(
                text=obj.properties["text"],
                collection_name=collection_name,
                tenant_name=tenant_name,
                vector=next(obj.vector.values()) if obj.vector else None,
            )
            for obj in response.objects
        ]

    async def __aenter__(self):
        self.__client = _async_client()
        self.__client.connect()
        collection = self.__client.collections.get(
            self.collection_name,
        )
        return collection.with_tenant(self.tenant_name)

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.__client.close()
