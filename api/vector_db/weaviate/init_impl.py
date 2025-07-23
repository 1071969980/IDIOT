
from typing import Optional, Sequence
from weaviate.classes.config import Property, Configure
from .constant import _client

def _create_data_collection_multi_tenancy(
    collection_name: str, 
    tenent_name: str | None, 
    properties: Optional[Sequence[Property]] = None) -> None:
    # Create collection with multi-tenancy
    with _client() as client:
        if client.collections.exists(collection_name):
            collection = client.collections.get(collection_name)
            if tenent_name:
                tenants = collection.tenants.get()
                if tenent_name in tenants:
                    msg = f"Collection {collection_name} and Tenent {tenent_name} already exists"
                    raise RuntimeError(msg)
                collection.tenants.create(tenent_name)
                return
        collection = client.collections.create(
            name=collection_name,
            multi_tenancy_config=Configure.multi_tenancy(
                enabled=True,
                auto_tenant_activation=True,
            ),
            properties=properties,
        )
        if tenent_name:
            collection.tenants.create(tenent_name)

def _create_data_collection_tenent(collection_name: str, tenent_name: str) -> None:
    with _client() as client:
        if not client.collections.exists(collection_name):
            msg = f"Collection {collection_name} does not exist"
            raise RuntimeError(msg)
        collection = client.collections.get(collection_name)
        if tenent_name in collection.tenants.get():
            msg = f"Tenent {tenent_name} already exists in collection {collection_name}"
            raise RuntimeError(msg)
        collection.tenants.create(tenent_name)
