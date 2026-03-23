import weaviate
from weaviate.client import WeaviateClient, WeaviateAsyncClient

from api.core.env_config import storage_config

WEAVIATE_HOST_DOMAIN = storage_config.weaviate_host_domain
WEAVIATE_HOST_PORT = storage_config.weaviate_host_port
WEAVIATE_HOST_GRPC_PORT = storage_config.weaviate_host_grpc_port

def _client() -> WeaviateClient:
    client = weaviate.connect_to_local(
        host=WEAVIATE_HOST_DOMAIN,
        port=WEAVIATE_HOST_PORT,
        grpc_port=WEAVIATE_HOST_GRPC_PORT,
    )
    if not client.is_ready():
        raise RuntimeError("Weaviate is not ready")
    return client

def _async_client() -> WeaviateAsyncClient:
    client = weaviate.use_async_with_local(
        host=WEAVIATE_HOST_DOMAIN,
        port=WEAVIATE_HOST_PORT,
        grpc_port=WEAVIATE_HOST_GRPC_PORT,
    )
    ### need to invoke client.connect() or using with 'async with' keyword
    ### before check ready
    # if not client.is_ready():
    #     raise RuntimeError("Weaviate is not ready")
    return client