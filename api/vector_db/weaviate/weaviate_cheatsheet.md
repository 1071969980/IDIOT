# Weaviate 向量数据库开发小抄

## 连接管理

### 获取同步客户端
```python
from weaviate.client import WeaviateClient
import weaviate

# 基本连接
client = weaviate.connect_to_local(
    host="weaviate",
    port="8080",
    grpc_port="50051"
)

# 检查服务状态
if not client.is_ready():
    raise RuntimeError("Weaviate is not ready")

# 使用上下文管理器
with client:
    # 执行操作
    pass
```

### 获取异步客户端
```python
from weaviate.client import WeaviateAsyncClient
import weaviate

# 创建异步客户端（需要手动连接）
client = weaviate.use_async_with_local(
    host="weaviate",
    port="8080",
    grpc_port="50051"
)

# 使用方式
async with client:
    await client.connect()
    # 执行操作
```

## 集合和租户管理

### 创建集合和租户
```python
from weaviate.classes.config import Property, Configure

# 创建带多租户的集合
async def create_collection_with_tenant(
    collection_name: str,
    tenant_name: str | None,
    properties: list[Property] = None
):
    async with _async_client() as client:
        if await client.collections.exists(collection_name):
            collection = client.collections.get(collection_name)
            if tenant_name and tenant_name not in await collection.tenants.get():
                await collection.tenants.create(tenant_name)
        else:
            await client.collections.create(
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
                await (await client.collections.get(collection_name)).tenants.create(tenant_name)
```

### 获取租户上下文
```python
# 获取集合
collection = client.collections.get(collection_name)

# 切换到租户
tenant = collection.with_tenant(tenant_name)

# 现在所有操作都在这个租户上下文中执行
```

## 数据插入

### 单个对象插入
```python
from weaviate.util import generate_uuid5

# 基本插入
def insert_object(collection_name, tenant_name, text, vector):
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        # 生成确定性 UUID
        uuid = generate_uuid5(collection_name + tenant_name + text)

        tenant.data.insert(
            properties={"text": text},
            vector=vector,
            uuid=uuid
        )

# 使用数据类对象
def insert_object_from_dataclass(obj):
    if obj.vector is None:
        raise ValueError("Vector is required")

    collection_name = obj.collection_name or default_collection_name
    tenant_name = obj.tenant_name or default_tenant_name

    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        tenant.data.insert(
            properties={"text": obj.text},
            vector=obj.vector,
            uuid=generate_uuid5(collection_name + tenant_name + obj.text)
        )
```

### 批量插入
```python
from weaviate.collections.classes.data import DataObject

# 同步批量插入
def batch_insert_sync(collection_name, tenant_name, objects):
    # 验证数据一致性
    if not all(obj.collection_name == objects[0].collection_name for obj in objects):
        raise ValueError("All objects must have same collection name")
    if not all(obj.tenant_name == objects[0].tenant_name for obj in objects):
        raise ValueError("All objects must have same tenant name")
    if not all(obj.vector is not None for obj in objects):
        raise ValueError("All objects must have vector")

    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        # 使用固定大小批量
        with tenant.batch.fixed_size(len(objects)) as batch:
            for obj in objects:
                batch.add_object(
                    properties={"text": obj.text},
                    vector=obj.vector,
                    uuid=generate_uuid5(collection_name + tenant_name + obj.text)
                )
            batch.flush()

        # 检查失败对象
        failed_objects = tenant.batch.failed_objects
        for failed in failed_objects:
            print(f"Failed to insert: {failed.message}")

# 异步批量插入
async def batch_insert_async(collection_name, tenant_name, objects):
    async with _async_client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        data_objects = [
            DataObject(
                properties={"text": obj.text},
                vector=obj.vector,
                uuid=generate_uuid5(collection_name + tenant_name + obj.text)
            )
            for obj in objects
        ]

        await tenant.data.insert_many(data_objects)
```

## 数据查询

### 向量相似性搜索
```python
def search_by_vector(collection_name, tenant_name, query_vector, limit=10):
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        response = tenant.query.near_vector(
            near_vector=query_vector,
            limit=limit
        )

        results = []
        for obj in response.objects:
            results.append({
                "text": obj.properties["text"],
                "vector": next(obj.vector.values()),
                "score": obj.metadata.distance
            })

        return results
```

### 文本关键词搜索
```python
def search_by_text(collection_name, tenant_name, query, limit=10):
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        response = tenant.query.bm25(
            query=query,
            limit=limit
        )

        results = []
        for obj in response.objects:
            results.append({
                "text": obj.properties["text"],
                "vector": next(obj.vector.values()) if obj.vector else None,
                "score": obj.metadata.score
            })

        return results
```

### 混合搜索（向量 + 关键词）
```python
def hybrid_search(collection_name, tenant_name, query, query_vector, limit=10):
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        response = tenant.query.hybrid(
            query=query,
            vector=query_vector,
            limit=limit
        )

        return [
            {
                "text": obj.properties["text"],
                "vector": next(obj.vector.values()),
                "score": obj.metadata.score
            }
            for obj in response.objects
        ]
```

## 数据删除

### 按ID删除
```python
from weaviate.classes.query import Filter

def delete_by_ids(collection_name, tenant_name, ids):
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        tenant.data.delete_many(
            where=Filter.by_id().contains_any(ids)
        )
```

### 按条件删除
```python
def delete_by_condition(collection_name, tenant_name, condition_filter):
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        tenant.data.delete_many(where=condition_filter)
```

## 数据检查

### 检查对象是否存在
```python
def object_exists(collection_name, tenant_name, object_id):
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        return tenant.data.exists(object_id)
```

### 获取对象
```python
def get_object(collection_name, tenant_name, object_id):
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        obj = tenant.data.fetch_by_id(object_id)
        return {
            "text": obj.properties["text"],
            "vector": next(obj.vector.values()) if obj.vector else None
        }
```

## 过滤器构建

### 基本过滤器
```python
from weaviate.classes.query import Filter

# 等于过滤
Filter.by_property("text").equal("specific_text")

# 包含过滤
Filter.by_property("text").contains("substring")

# 大于小于
Filter.by_property("number").greater_than(100)
Filter.by_property("number").less_than(1000)

# 逻辑组合
Filter.all_of([
    Filter.by_property("text").contains("important"),
    Filter.by_property("number").greater_than(100)
])

Filter.any_of([
    Filter.by_property("text").contains("urgent"),
    Filter.by_property("text").contains("critical")
])
```

## 模式定义

### 属性定义
```python
from weaviate.classes.config import Property, DataType, Tokenization

# 文本属性
Property(
    name="text",
    data_type=DataType.TEXT,
    description="Text content",
    tokenization=Tokenization.TRIGRAM
)

# 数字属性
Property(
    name="number",
    data_type=DataType.NUMBER,
    description="Numeric value"
)

# 布尔属性
Property(
    name="is_active",
    data_type=DataType.BOOL,
    description="Active status"
)

# 日期属性
Property(
    name="created_at",
    data_type=DataType.DATE,
    description="Creation timestamp"
)
```

### 向量配置
```python
from weaviate.classes.config import Configure

# 自提供向量
Configure.Vectors.self_provided(
    vector_index_config=Configure.VectorIndex.dynamic()
)

# 自定义向量索引
Configure.Vectors.self_provided(
    vector_index_config=Configure.VectorIndex.hnsw(
        distance_metric=Configure.VectorIndex.DistanceMetric.COSINE,
        ef=100,
        ef_construction=128
    )
)
```

## 错误处理

### 连接错误
```python
try:
    client = weaviate.connect_to_local(host="weaviate", port=8080)
    if not client.is_ready():
        raise RuntimeError("Weaviate is not ready")
except Exception as e:
    print(f"Connection failed: {e}")
    raise
```

### 数据验证错误
```python
# 批量操作前的验证
def validate_batch_objects(objects):
    if not objects:
        raise ValueError("Objects list cannot be empty")

    # 检查集合名称一致性
    if not all(obj.collection_name == objects[0].collection_name for obj in objects):
        raise ValueError("All objects must have same collection name")

    # 检查租户名称一致性
    if not all(obj.tenant_name == objects[0].tenant_name for obj in objects):
        raise ValueError("All objects must have same tenant name")

    # 检查向量完整性
    if not all(obj.vector is not None for obj in objects):
        raise ValueError("All objects must have vector")

    return True
```

## 性能优化

### 批量操作最佳实践
```python
def optimized_batch_insert(collection_name, tenant_name, objects, batch_size=100):
    """分批插入大量数据"""
    with _client() as client:
        collection = client.collections.get(collection_name)
        tenant = collection.with_tenant(tenant_name)

        # 分批处理
        for i in range(0, len(objects), batch_size):
            batch = objects[i:i + batch_size]

            with tenant.batch.fixed_size(len(batch)) as batch_op:
                for obj in batch:
                    batch_op.add_object(
                        properties={"text": obj.text},
                        vector=obj.vector,
                        uuid=generate_uuid5(collection_name + tenant_name + obj.text)
                    )
                batch_op.flush()

            # 检查并处理失败的对象
            if tenant.batch.failed_objects:
                print(f"Batch {i//batch_size} had failures")
```

## 常用配置

### 环境变量配置
```python
import os

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "weaviate")
WEAVIATE_PORT = os.getenv("WEAVIATE_PORT", "8080")
WEAVIATE_GRPC_PORT = os.getenv("WEAVIATE_GRPC_PORT", "50051")
```

### 默认参数
```python
DEFAULT_COLLECTION_NAME = "default_collection"
DEFAULT_TENANT_NAME = "default_tenant"
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_BATCH_SIZE = 100
```

这个开发小抄涵盖了 Weaviate 向量数据库的常用操作模式，可以直接作为参考实现。