import os
import weaviate
from weaviate.client import WeaviateClient, WeaviateAsyncClient

WEAVIATE_HOST_DOMAIN = os.getenv("WEAVIATE_HOST_DOMAIN") or "weaviate"
WEAVIATE_HOST_PORT = os.getenv("WEAVIATE_HOST_PORT") or "8080"
WEAVIATE_HOST_GRPC_PORT = os.getenv("WEAVIATE_HOST_GRPC_PORT") or "50051"

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
    if not client.is_ready():
        raise RuntimeError("Weaviate is not ready")
    return client