from typing import Any

import logfire
from weaviate.classes.query import Filter
from weaviate.collections import Collection
from weaviate.collections.classes.types import WeaviateProperties
from weaviate.util import generate_uuid5

from api.vector_db.vector_db_base import BaseVectorDB
from api.vector_db.weaviate.constant import _client

from .simple_text_def import SimpleTextObeject_Weaviate


class SimpleTextVectorDB_Weaviate(BaseVectorDB[SimpleTextObeject_Weaviate]):
    def __init__(self, collection_name: str, tenant_name: str) -> None:
        self.collection_name = collection_name
        self.tenant_name = tenant_name

    def add_object(self,
                    obj: SimpleTextObeject_Weaviate,
                    **kwargs: dict[str, Any]) -> None:
        with _client() as client:
            if obj.vector is None:
                raise ValueError("Vector is required")
            collection_name = obj.collection_name or self.collection_name
            tenant_name = obj.tenant_name or self.tenant_name
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            tenant.data.insert(
                properties = {
                    "text": obj.text,
                },
                vector=obj.vector,
                uuid=generate_uuid5(collection_name + tenant_name + obj.text),
            )

    def add_objects(self,
                    objs: list[SimpleTextObeject_Weaviate],
                    **kwargs: dict[str, Any]) -> None:
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
        with _client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            with tenant.batch.fixed_size(len(objs)) as batch:
                for obj in objs:
                    batch.add_object(
                        properties = {
                            "text": obj.text,
                        },
                        vector=obj.vector,
                        uuid=generate_uuid5(collection_name + tenant_name + obj.text),
                    )
            failed_objects = tenant.batch.failed_objects
            for failed_object in failed_objects:
                logfire.warning("Failed to add object when weaviate batch importing: {failed_msg}",
                              failed_msg=failed_object.message,
                              )

    def id_exists(self, id: str) -> bool:
        collection_name = self.collection_name
        tenant_name = self.tenant_name
        with _client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            return tenant.data.exists(id)
            

    def delete_by_ids(self, ids: list[str]) -> None:
        collection_name = self.collection_name
        tenant_name = self.tenant_name
        with _client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            tenant.data.delete_many(
                where=Filter.by_id().contains_any(ids),
            )

    def search_ids_by_metadata_field(self, key: str, value: Any):
        raise NotImplementedError

    def delete_by_metadata_field(self, key, value):
        raise NotImplementedError

    def search_by_vector(self,
                         query_vector: list[float] | dict[str, list[float]],
                         **kwargs: dict[str, Any]) -> list[SimpleTextObeject_Weaviate]:
        collection_name = self.collection_name
        tenant_name = self.tenant_name
        with _client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            response = tenant.query.near_vector(
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

    def search_by_text(self, query: str, **kwargs: dict[str, Any]):
        """
        keyword search by bm25
        """
        collection_name = self.collection_name
        tenant_name = self.tenant_name
        with _client() as client:
            collection = client.collections.get(collection_name)
            tenant = collection.with_tenant(tenant_name)
            response = tenant.query.bm25(
                query,
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

    def __enter__(self) -> Collection[WeaviateProperties, None]:
        self.__client = _client()
        collection = self.__client.collections.get(
            self.collection_name,
        )
        return collection.with_tenant(self.tenant_name)

    def __exit__(self, exc_type, exc_value, traceback):
        self.__client.close()
        if exc_type:
            return False
