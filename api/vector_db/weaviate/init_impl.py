
from typing import Optional, Sequence
from weaviate.classes.config import Property, Configure
from .constant import _client

def _create_data_collection_multi_tenancy(
    collection_name: str, 
    tenant_name: str | None, 
    properties: Optional[Sequence[Property]] = None) -> None:
    # Create collection with multi-tenancy
    with _client() as client:
        if client.collections.exists(collection_name):
            collection = client.collections.get(collection_name)
            if tenant_name:
                tenants = collection.tenants.get()
                if tenant_name in tenants:
                    msg = f"Collection {collection_name} and tenant {tenant_name} already exists"
                    raise RuntimeError(msg)
                collection.tenants.create(tenant_name)
                return
        collection = client.collections.create(
            name=collection_name,
            multi_tenancy_config=Configure.multi_tenancy(
                enabled=True,
                auto_tenant_activation=True,
            ),
            properties=properties,
            vector_index_config=Configure.VectorIndex.dynamic(),
        )
        if tenant_name:
            collection.tenants.create(tenant_name)

def _create_data_collection_tenant(collection_name: str, tenant_name: str) -> None:
    with _client() as client:
        if not client.collections.exists(collection_name):
            msg = f"Collection {collection_name} does not exist"
            raise RuntimeError(msg)
        collection = client.collections.get(collection_name)
        if tenant_name in collection.tenants.get():
            msg = f"tenant {tenant_name} already exists in collection {collection_name}"
            raise RuntimeError(msg)
        collection.tenants.create(tenant_name)
