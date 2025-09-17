
from typing import Optional, Sequence
from weaviate.classes.config import Property, Configure
from .constant import _client, _async_client

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
            vector_config=Configure.Vectors.self_provided(
                vector_index_config=Configure.VectorIndex.dynamic(),
            )
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

async def create_collection_or_tenant(
    collection_name: str, 
    tenant_name: str | None, 
    properties: Sequence[Property] | None = None,
    raise_if_collection_exists: bool = False,
    raise_if_tenant_exists: bool = False
) -> None:
    """
    Create a collection with multi-tenancy and/or a tenant within an existing collection.
    
    Args:
        collection_name: Name of the collection to create
        tenant_name: Name of the tenant to create (optional)
        properties: Properties for the collection (only used when creating new collection)
        raise_if_collection_exists: If True, raise exception when collection already exists
        raise_if_tenant_exists: If True, raise exception when tenant already exists
    
    Raises:
        CollectionExistsError: If collection already exists and raise_if_collection_exists is True
        TenantExistsError: If tenant already exists and raise_if_tenant_exists is True
    """
    class CollectionExistsError(Exception):
        """Raised when attempting to create a collection that already exists"""
        pass
    
    class TenantExistsError(Exception):
        """Raised when attempting to create a tenant that already exists"""
        pass
    
    async with _async_client() as client:
        if await client.collections.exists(collection_name):
            if raise_if_collection_exists:
                raise CollectionExistsError(f"Collection '{collection_name}' already exists")
            
            collection = client.collections.get(collection_name)
            if tenant_name:
                tenants = await collection.tenants.get()
                if tenant_name in tenants and raise_if_tenant_exists:
                    raise TenantExistsError(f"Tenant '{tenant_name}' already exists in collection '{collection_name}'")
                if tenant_name not in tenants:
                    await collection.tenants.create(tenant_name)
            return
        
        # Create new collection
        collection = await client.collections.create(
            name=collection_name,
            multi_tenancy_config=Configure.multi_tenancy(
                enabled=True,
                auto_tenant_activation=True,
            ),
            properties=properties,
            vector_config=Configure.Vectors.self_provided(
                vector_index_config=Configure.VectorIndex.dynamic(),
            )
        )
        
        if tenant_name:
            await collection.tenants.create(tenant_name)
