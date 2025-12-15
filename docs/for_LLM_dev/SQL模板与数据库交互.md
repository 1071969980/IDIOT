
# SQL 与 PostgreSQL 交互范式

本项目采用基于文件的 SQL 模板系统与 PostgreSQL 进行交互，避免了 ORM 的复杂性，保持了 SQL 的原生能力。

**核心特点**：
- SQL 语句按功能块组织在 `.sql` 文件中，使用 `--` 注释作为分隔符
- 使用 `parse_sql_file()` 自动解析 SQL 文件为 Python 变量
- 基于 `@dataclass` 的数据模型和异步数据库操作
- 统一的错误处理模式和参数化查询
- 触发器和其他数据库对象集成到表创建流程中

## parse_sql_file() 机制

`parse_sql_file()` 函数解析 SQL 文件的规则：
- 以 `--` 开头的行被视为注释块
- 注释块的最后一行作为 SQL 语句的键名（去除 `--` 前缀）
- 注释块后的非空行作为 SQL 语句内容
- 重复键名会被覆盖，后出现的有效
- **重要**: 使用 `--\n`（单独的 `--` 行加换行）作为分隔符时，多个SQL语句会被解析到同一个Python list[str]变量中

示例格式：
```sql
-- This is a comment block
-- The last line becomes the key
SELECT * FROM table_name WHERE id = :id;

-- Single comment line
INSERT INTO table_name (column_name) VALUES (:value);

-- CreateTablesAndIndexes (会被解析为list[str])
CREATE TABLE IF NOT EXISTS table_name (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    column_name VARCHAR(100) NOT NULL
);
--
CREATE INDEX idx_table_name_column ON table_name(column_name);
--
CREATE INDEX idx_table_name_field ON table_name(field_name);
```

**解析结果**：
- `"This is a comment block"` → `"SELECT * FROM table_name WHERE id = :id;"`
- `"Single comment line"` → `"INSERT INTO table_name (column_name) VALUES (:value);"`
- `"CreateTablesAndIndexes"` → `["CREATE TABLE...", "CREATE INDEX idx_table_name_column...", "CREATE INDEX idx_table_name_field..."]`

## 文件夹结构

```
api/[module]/sql_stat/[table_name]/
├── TableName.sql         # SQL 语句定义（通常使用 PascalCase 或驼峰命名）
├── utils.py              # 数据访问层和模型
└── __init__.py           # 可选的包初始化文件
```

sql_stat下也可以没有table_name一级的文件夹, 如：
```
api/[module]/sql_stat/
├── TableName.sql
├── utils.py
└── __init__.py
```


**命名约定示例**：
- `ModuleNameEntity.sql` - 驼峰命名 + 缩写
- `EntityTable.sql` - PascalCase
- `module_entities.sql` - 下划线命名

## 最简代码示例

**SQL 文件** (`ModuleNameEntity.sql`):
```sql
-- InsertEntity
INSERT INTO module_entities (owner_id, session_id, sequence_index, entity_type, content, json_data, status, task_id)
VALUES (:owner_id, :session_id, :sequence_index, :entity_type, :content, :json_data, :status, :task_id)
RETURNING id;

-- QueryEntityById
SELECT * FROM module_entities WHERE id = :id_value;

-- CreateEntitiesTable
CREATE TABLE IF NOT EXISTS module_entities (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    owner_id UUID NOT NULL,
    session_id UUID NOT NULL,
    -- ... 其他字段定义
);
--
CREATE INDEX IF NOT EXISTS idx_module_entities_session_id ON module_entities (session_id);
--
CREATE INDEX IF NOT EXISTS idx_module_entities_owner_id ON module_entities (owner_id);
```

**utils.py**:
```python
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy import text
from pathlib import Path

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# 解析SQL文件
sql_file_path = Path(__file__).parent / "ModuleNameEntity.sql"
sql_statements = parse_sql_file(sql_file_path)

INSERT_ENTITY = sql_statements["InsertEntity"]
QUERY_ENTITY_BY_ID = sql_statements["QueryEntityById"]
CREATE_ENTITIES_TABLE = sql_statements["CreateEntitiesTable"]  # 这是一个list[str]

@dataclass
class _EntityCreate:
    """创建实体的数据模型"""
    owner_id: UUID
    session_id: UUID
    sequence_index: int
    entity_type: str
    content: str
    status: str
    json_data: Optional[Dict[str, Any]] = None
    task_id: Optional[UUID] = None

async def create_table() -> None:
    """创建表和索引 - 处理list[str]类型的SQL语句"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # CREATE_ENTITIES_TABLE 是一个list，需要逐条执行
        for stmt in CREATE_ENTITIES_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()

async def insert_entity(entity_data: _EntityCreate) -> UUID:
    """插入新实体 - 数据库自动生成UUID"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(INSERT_ENTITY), {
            "owner_id": entity_data.owner_id,
            "session_id": entity_data.session_id,
            "sequence_index": entity_data.sequence_index,
            "entity_type": entity_data.entity_type,
            "content": entity_data.content,
            "json_data": entity_data.json_data,
            "status": entity_data.status,
            "task_id": entity_data.task_id,
        })
        await conn.commit()
        # 使用RETURNING id获取数据库生成的UUID
        return result.scalar()
```

## 关系说明

1. **SQL 文件**：定义所有数据库操作的 SQL 语句模板
2. **utils.py**：
   - 解析 SQL 文件为常量
   - 定义数据模型（`@dataclass`）
   - 实现异步数据库操作函数
3. **外部使用**：通过导入 utils.py 中的函数进行数据库操作

## 高级功能模式

### 1. 批量操作

**SQL 定义**：
```sql
-- InsertEntitiesBatch
INSERT INTO module_entities (owner_id, session_id, sequence_index, entity_type, content, json_data, status, task_id)
SELECT
    unnest(:owner_ids_list) as owner_id,
    unnest(:session_ids_list) as session_id,
    unnest(:sequence_indices_list) as sequence_index,
    unnest(:entity_types_list) as entity_type,
    unnest(:contents_list) as content,
    unnest(:json_data_list) as json_data,
    unnest(:statuses_list) as status,
    unnest(:task_ids_list) as task_id
RETURNING id;

-- UpdateEntityStatusByIds
UPDATE module_entities
SET status = :status_value
WHERE id IN :ids_list;
```

**Python 实现**：
```python
@dataclass
class _EntityBatchCreate:
    owner_ids: list[UUID]
    session_ids: list[UUID]
    sequence_indices: list[int]
    entity_types: list[str]
    contents: list[str]
    json_data: list[Optional[Dict[str, Any]]]
    statuses: list[str]
    task_ids: list[Optional[UUID]]

async def insert_entities_batch(entities_data: _EntityBatchCreate) -> list[UUID]:
    """批量插入实体"""
    # 验证所有列表长度一致
    list_lengths = [len(entities_data.owner_ids), len(entities_data.session_ids), ...]
    if len(set(list_lengths)) != 1:
        raise ValueError("All input lists must have the same length")

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_ENTITIES_BATCH).bindparams(
                bindparam("owner_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("session_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                # ... 其他参数类型定义
            ),
            {
                "owner_ids_list": entities_data.owner_ids,
                "session_ids_list": entities_data.session_ids,
                # ... 其他参数值
            }
        )
        await conn.commit()
        return [row[0] for row in result.fetchall()]

async def update_entity_status_by_ids(
    entity_ids: list[UUID],
    new_status: str
) -> int:
    """批量更新状态"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_ENTITY_STATUS_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {"status_value": new_status, "ids_list": entity_ids}
        )
        await conn.commit()
        return result.rowcount

async def create_entities_from_list(entities: list[_EntityCreate]) -> list[UUID]:
    """从单个对象列表批量创建实体的便捷函数"""
    if not entities:
        return []

    batch_data = _EntityBatchCreate(
        owner_ids=[entity.owner_id for entity in entities],
        session_ids=[entity.session_id for entity in entities],
        sequence_indices=[entity.sequence_index for entity in entities],
        entity_types=[entity.entity_type for entity in entities],
        contents=[entity.content for entity in entities],
        json_data=[entity.json_data for entity in entities],
        statuses=[entity.status for entity in entities],
        task_ids=[entity.task_id for entity in entities]
    )

    return await insert_entities_batch(batch_data)
```

**使用建议**：
- 提供从单个对象列表到 BatchCreate 的转换函数，简化批量操作的调用
- 使用列表推导式确保数据一致性，避免手动拼接错误
- 添加空列表检查，提升用户体验

### 2. 动态字段查询

**SQL 定义**：
```sql
-- QueryEntityField1
SELECT :field_name_1 FROM module_entities WHERE id = :id_value;

-- QueryEntityField2
SELECT :field_name_1, :field_name_2 FROM module_entities WHERE id = :id_value;

-- UpdateEntity1
UPDATE module_entities SET :field_name_1 = :field_value_1 WHERE id = :id_value;
```

**Python 实现**：
```python
async def get_entity_fields(
    entity_id: UUID,
    field_names: list[str]
) -> Optional[Dict[str, Any]]:
    """动态查询指定字段"""
    field_count = len(field_names)

    # 根据字段数量选择SQL模板
    if field_count == 1:
        sql = QUERY_ENTITY_FIELD_1
    elif field_count == 2:
        sql = QUERY_ENTITY_FIELD_2
    # ... 更多字段支持

    # 动态替换字段名占位符
    params = {"id_value": entity_id}
    for i, field_name in enumerate(field_names, 1):
        sql = sql.replace(f":field_name_{i}", field_name)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}

async def update_entity_fields(
    update_data: _EntityUpdate
) -> bool:
    """动态更新指定字段"""
    field_count = len(update_data.fields)

    # 根据字段数量选择SQL模板
    if field_count == 1:
        sql = UPDATE_ENTITY_1
    elif field_count == 2:
        sql = UPDATE_ENTITY_2
    # ... 更多字段支持

    # 动态替换字段名和值
    params = {"id_value": update_data.entity_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        sql = sql.replace(f":field_name_{i}", field)
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0
```

### 3. 触发器和数据库对象集成

**SQL 定义**：
```sql
-- CreateEntityTriggers
CREATE OR REPLACE FUNCTION module_entity_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER module_entity_before_update
BEFORE UPDATE ON module_entities
FOR EACH ROW
EXECUTE FUNCTION module_entity_update_timestamp();
```

**Python 实现**：
```python
async def create_table() -> None:
    """创建表和所有相关数据库对象"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # 创建表和索引
        for stmt in CREATE_ENTITIES_TABLE:
            await conn.execute(text(stmt))

        # 创建触发器和函数
        for stmt in CREATE_ENTITY_TRIGGERS:
            await conn.execute(text(stmt))

        await conn.commit()
```

## 数据库初始化时机

**重要原则**：表的初始化应当由外界程序主动调用，而不是在导入包时自动执行。

### 推荐的初始化模式

**错误的做法**（避免）：
```python
# utils.py - 错误：在导入时自动初始化
from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# 解析SQL文件
sql_file_path = Path(__file__).parent / "ModuleNameEntity.sql"
sql_statements = parse_sql_file(sql_file_path)

# 错误：在模块级别自动执行初始化
async def _auto_init():
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_ENTITIES_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()

# 导入模块时自动执行初始化（应当避免）
import asyncio
asyncio.create_task(_auto_init())
```

**正确的做法**（推荐）：
```python
# utils.py - 正确：只提供初始化函数
from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# 解析SQL文件
sql_file_path = Path(__file__).parent / "ModuleNameEntity.sql"
sql_statements = parse_sql_file(sql_file_path)

# 提供初始化函数，但不自动调用
async def create_table() -> None:
    """创建表和索引 - 供外部程序主动调用"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_ENTITIES_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()
```

### 外部程序调用示例

应用程序启动时显式调用初始化：
```python
# main.py 或应用启动脚本
from api.module_name_entity.sql_stat.utils import create_table
from api.user_module.sql_stat.utils import create_user_table

async def init_database():
    """应用启动时主动初始化数据库表"""
    try:
        await create_table()
        await create_user_table()
        # ... 其他表的初始化
        print("数据库表初始化完成")
    except Exception as e:
        print(f"数据库表初始化失败: {e}")
        raise

# 应用启动时调用
async def main():
    await init_database()
    # ... 其他应用逻辑

if __name__ == "__main__":
    asyncio.run(main())
```

### 为什么要避免导入时自动初始化

1. **可控性**：外部程序可以控制初始化时机，避免在不合适的时机执行数据库操作
2. **错误处理**：可以在应用启动时集中处理初始化错误
3. **测试友好**：测试环境可以选择性地初始化所需表结构
4. **依赖管理**：避免循环依赖和初始化顺序问题
5. **资源控制**：避免在不需要时过早占用数据库连接

## UUID 设计规则

**具体规则**：

1. **数据库层面**：
   - 使用 `id UUID PRIMARY KEY DEFAULT uuidv7()` 让数据库自动生成UUID，不再提供其他UUID字段
   - INSERT语句使用 `RETURNING id` 子句立即返回生成的UUID
   - 不在INSERT语句中手动传入UUID参数

2. **Python层面**：
   - **不主动生成UUID**：移除所有 `uuid4()` 调用

3. **数据模型**：
   - Python数据模型中UUID字段使用 `UUID` 类型
   - 创建操作的数据模型不应包含UUID字段

**正确示例**：

```sql
-- 正确的INSERT语句
INSERT INTO entities (owner_id, content)
VALUES (:owner_id, :content)
RETURNING id;
```

```python
# 正确的Python处理
async def create_entity(data: EntityCreate) -> UUID:
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_ENTITY),
            {"owner_id": data.owner_id, "content": data.content}
        )
        await conn.commit()

        return result.scalar()
```

**错误示例**：
```python
# 错误：Python生成UUID
entity_id = uuid4()
await conn.execute(text(INSERT), {"id": entity_id, ...})
```

## PostgreSQL 方言语法最佳实践

### 1. 强制使用 PostgreSQL 语法

在本项目中，**所有 SQL 语句都应使用 PostgreSQL 方言语法**，避免使用 ANSI SQL 或跨数据库兼容性语法。

**必须使用的 PostgreSQL 特性**：

1. **UUID 生成**：
```sql
-- 正确：使用 PostgreSQL 的 uuidv7() 函数
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    -- 其他字段
);

-- 错误：避免使用 SQL 标准或其他数据库语法
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT (SELECT uuid4()),  -- 避免这种写法
    -- 其他字段
);
```

2. **JSON 数据类型**：
```sql
-- 正确：使用 PostgreSQL 的 JSONB 类型
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    metadata JSONB NOT NULL DEFAULT '{}',
    -- 其他字段
);

-- JSONB 查询语法
SELECT * FROM entities
WHERE metadata @> '{"status": "active"}'::jsonb;

-- 错误：避免使用 TEXT 存储JSON
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    metadata TEXT,  -- 避免这种写法
    -- 其他字段
);
```

3. **数组操作**：
```sql
-- 正确：使用 PostgreSQL 的 unnest 函数
INSERT INTO entities (owner_id, tags)
SELECT
    unnest(:owner_ids_list) as owner_id,
    unnest(:tags_list) as tags;

-- 正确：数组类型定义
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    tags UUID[] NOT NULL DEFAULT '{}',
    -- 其他字段
);

-- 错误：避免使用字符串拼接
INSERT INTO entities (owner_id, tags)
VALUES (:owner_id, :tags_string);  -- 避免这种写法
```

4. **索引和约束**：
```sql
-- 正确：PostgreSQL 特有的索引类型
CREATE INDEX CONCURRENTLY idx_entities_metadata_gin
ON entities USING GIN (metadata);

CREATE INDEX idx_entities_name_trgm
ON entities USING GIN (name gin_trgm_ops);

-- 正确：部分索引
CREATE INDEX idx_entities_active
ON entities (owner_id)
WHERE status = 'active';
```

### 2. 常见语法易混淆情况示例

1. **字符串拼接**：
```sql
-- 正确：PostgreSQL 语法
SELECT name || ' - ' || description FROM entities;

-- 错误：MySQL 语法（不应使用）
SELECT CONCAT(name, ' - ', description) FROM entities;
```

2. **日期时间函数**：
```sql
-- 正确：PostgreSQL 语法
SELECT NOW() + INTERVAL '1 day';
SELECT EXTRACT(EPOCH FROM created_at);

-- 错误：其他数据库语法（不应使用）
SELECT DATE_ADD(NOW(), INTERVAL 1 DAY);  -- MySQL
SELECT DATEADD(day, 1, GETDATE());       -- SQL Server
```

3. **布尔值处理**：
```sql
-- 正确：PostgreSQL 布尔语法
SELECT * FROM entities WHERE is_active = true;
UPDATE entities SET is_active = false;

-- 错误：其他数据库语法（不应使用）
SELECT * FROM entities WHERE is_active = 1;     -- 数值形式
UPDATE entities SET is_active = 0;              -- 数值形式
```

4. **自增ID**：
```sql
-- 正确：PostgreSQL SERIAL 或 IDENTITY
CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    -- 或者使用 IDENTITY（PostgreSQL 10+）
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
);

-- 错误：其他数据库语法（不应使用）
CREATE TABLE entities (
    id INT AUTO_INCREMENT PRIMARY KEY  -- MySQL 语法
);
```

5. **LIMIT/OFFSET**：
```sql
-- 正确：PostgreSQL 语法
SELECT * FROM entities
ORDER BY created_at DESC
LIMIT 10 OFFSET 20;

-- 正确：使用 FETCH FIRST（PostgreSQL 12+）
SELECT * FROM entities
ORDER BY created_at DESC
FETCH FIRST 10 ROWS ONLY
OFFSET 20 ROWS;

-- 错误：SQL Server 语法（不应使用）
SELECT TOP 10 * FROM entities;  -- 不应使用
```

6. **空值处理**：
```sql
-- 正确：PostgreSQL 语法
SELECT COALESCE(name, 'Unknown') FROM entities;
SELECT NULLIF(status, 'pending') FROM entities;

-- 错误：其他数据库语法（不应使用）
SELECT IFNULL(name, 'Unknown') FROM entities;   -- MySQL 语法
SELECT ISNULL(name, 'Unknown') FROM entities;    -- SQL Server 语法
```

7. **正则表达式**：
```sql
-- 正确：PostgreSQL 语法
SELECT * FROM entities
WHERE name ~ '^[A-Z][a-z]+$';

SELECT * FROM entities
WHERE email ~* '^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$';

-- 错误：其他数据库语法（不应使用）
SELECT * FROM entities
WHERE name REGEXP '^[A-Z][a-z]+$';  -- MySQL 语法
```

8. **INSERT...ON CONFLICT**：
```sql
-- 正确：PostgreSQL 语法
INSERT INTO entities (id, name, status)
VALUES (:id, :name, :status)
ON CONFLICT (id)
DO UPDATE SET
    status = EXCLUDED.status,
    updated_at = NOW();

-- 错误：其他数据库语法（不应使用）
INSERT INTO entities (id, name, status)
VALUES (:id, :name, :status)
ON DUPLICATE KEY UPDATE  -- MySQL 语法
    status = VALUES(status);
```

9. **数组操作符**：
```sql
-- 正确：PostgreSQL 数组语法
SELECT * FROM entities
WHERE tags @> ARRAY['tag1', 'tag2'];  -- 包含

SELECT * FROM entities
WHERE tags && ARRAY['tag1', 'tag2'];  -- 交集

-- 错误：避免使用字符串处理数组
SELECT * FROM entities
WHERE tags LIKE '%tag1%';  -- 不应使用
```

### 3. 开发时注意事项

1. **禁止使用其他数据库语法**：所有 SQL 语句必须使用 PostgreSQL 方言语法
2. **充分利用 PostgreSQL 特性**：如 JSONB、数组类型、高级索引等
3. **保持语法一致性**：在整个项目中使用统一的 PostgreSQL 语法风格
4. **测试时注意版本**：确保使用的语法在项目 PostgreSQL 版本中支持

## SQLAlchemy 类型注解最佳实践

### 为什么需要显式类型注解

在异步数据库操作中，显式指定 SQLAlchemy 类型注解是必要的，原因如下：

1. **类型安全**：确保传入的参数类型与数据库字段类型匹配
2. **批量操作支持**：在 `expanding=True` 参数中需要明确指定类型
3. **驱动兼容性**：不同数据库驱动对类型处理方式不同
4. **性能优化**：正确的类型注解可以提升查询性能

### 常用类型对照表

| Python 类型 | SQLAlchemy 类型 | 导入路径 | 使用场景 |
|-------------|----------------|----------|----------|
| `str` | `TEXT` | `from sqlalchemy.dialects.postgresql import TEXT` | 文本字段 |
| `int` | `INTEGER` | `from sqlalchemy.dialects.postgresql import INTEGER` | 整数字段 |
| `dict` | `JSONB` | `from sqlalchemy.dialects.postgresql import JSONB` | JSON数据 |
| `list` | `ARRAY` | `from sqlalchemy.dialects.postgresql import ARRAY` | 数组字段 |
| `UUID` | `UUID` | `from sqlalchemy.dialects.postgresql import UUID as SQLTYPE_UUID` | UUID字段 |

### SQLTYPE_UUID 的使用示例

```python
from sqlalchemy.dialects.postgresql import ARRAY, UUID as SQLTYPE_UUID, INTEGER, JSONB
from sqlalchemy import text, bindparam
from uuid import UUID

# 正确的使用方式
async def batch_insert_entities(entity_ids: list[UUID], owner_ids: list[UUID]) -> bool:
    """批量插入实体记录，正确使用类型注解"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_ENTITIES_BATCH).bindparams(
                bindparam("entity_ids_list", type_=ARRAY(SQLTYPE_UUID)),  # 明确指定UUID数组类型
                bindparam("owner_ids_list", type_=ARRAY(SQLTYPE_UUID)),   # 明确指定UUID数组类型
            ),
            {
                "entity_ids_list": entity_ids,
                "owner_ids_list": owner_ids,
            },
        )
        await conn.commit()
        return result.rowcount > 0

# 单个UUID参数也需要类型注解
async def update_entity_by_id(entity_id: UUID, task_id: UUID) -> bool:
    """更新单个实体记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_ENTITY_BY_ID).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),           # 单个UUID参数
                bindparam("task_id_value", type_=SQLTYPE_UUID),  # 单个UUID参数
            ),
            {
                "id_value": entity_id,
                "task_id_value": task_id,
            },
        )
        await conn.commit()
        return result.rowcount > 0
```

### expanding=True 参数的作用和使用场景

`expanding=True` 是 SQLAlchemy 的一个重要功能，用于将 Python 列表参数动态展开为 SQL 表达式。

#### expanding=True 的作用

1. **列表展开**：将 Python 列表自动转换为 SQL 中适用的格式
2. **IN 子句支持**：最常用于 `WHERE column IN :param` 场景
3. **动态参数数量**：允许在运行时决定参数数量，编译时不需要固定

#### 何时使用 expanding=True

**适用场景**：
- SQL 语句中使用 `IN (...)` 操作符
- 需要传入可变数量的参数
- 批量查询、更新或删除操作

**SQL 模板示例**：
```sql
-- DeleteEntitiesByIds
DELETE FROM module_entities WHERE id IN :ids_list;

-- QueryEntitiesByIds
SELECT * FROM module_entities WHERE id IN :ids_list;
```

#### 正确的使用方式

```python
# 正确：expanding=True 用于 IN 子句
async def delete_entities_by_ids(entity_ids: list[UUID]) -> int:
    """批量删除实体记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_ENTITIES_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {
                "ids_list": entity_ids,  # 列表会自动展开为 IN (id1, id2, id3, ...)
            },
        )
        await conn.commit()
        return result.rowcount

# 正确：expanding=True 用于批量查询
async def query_entities_by_ids(entity_ids: list[UUID]) -> list[dict]:
    """根据ID列表查询实体记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_ENTITIES_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {"ids_list": entity_ids}
        )
        return [dict(row) for row in result.fetchall()]
```

#### expanding=True 的工作原理

当 `expanding=True` 时：
1. **编译时**：SQLAlchemy 将 `:ids_list` 标记为可扩展参数
2. **执行时**：将 Python 列表 `[uuid1, uuid2, uuid3]` 展开为多个独立的绑定参数
3. **最终SQL**：`WHERE id IN (:ids_list_1, :ids_list_2, :ids_list_3)`

#### 与 ARRAY 类型的区别

**expanding=True**：
- 用于 `IN (...)` 操作符
- 将列表展开为多个独立的参数
- 每个元素都是独立的绑定参数

**ARRAY 类型**：
- 用于 PostgreSQL 数组字段
- 整个列表作为一个参数传递
- 与 `unnest()` 函数配合使用

```python
# expanding=True - IN 子句
text("DELETE FROM table WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True, type_=SQLTYPE_UUID)
)
# 生成：DELETE FROM table WHERE id IN (:ids_1, :ids_2, :ids_3)

# ARRAY 类型 - 数组字段
text("INSERT INTO table (ids) VALUES (:ids)").bindparams(
    bindparam("ids", type_=ARRAY(SQLTYPE_UUID))
)
# 生成：INSERT INTO table (ids) VALUES (ARRAY[uuid1, uuid2, uuid3])
```

### 类型别名的重要性

使用 `SQLTYPE_UUID` 作为别名可以避免与 Python 标准库的 `UUID` 冲突：

```python
# 推荐的导入方式
from sqlalchemy.dialects.postgresql import UUID as SQLTYPE_UUID
from uuid import UUID  # Python标准库的UUID类型

# 在代码中明确区分
python_uuid: UUID = uuid4()           # Python UUID对象
sqlalchemy_uuid_type = SQLTYPE_UUID    # SQLAlchemy UUID类型
```

### 常见错误和解决方案

**错误1：缺少类型注解导致批量操作失败**
```python
# 错误：缺少类型注解
result = await conn.execute(
    text(INSERT_BATCH),  # 没有指定参数类型
    {"ids_list": memory_ids}  # 可能导致类型错误
)

# 正确：指定明确的类型注解
result = await conn.execute(
    text(INSERT_BATCH).bindparams(
        bindparam("ids_list", type_=ARRAY(SQLTYPE_UUID)),
    ),
    {"ids_list": memory_ids}
)
```

**错误2：expanding 参数与类型不匹配**
```python
# 错误：expanding=True 但类型不是数组
result = await conn.execute(
    text(DELETE_BY_IDS).bindparams(
        bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),  # 错误：应该是ARRAY类型
    ),
    {"ids_list": memory_ids}
)

# 正确：使用 ARRAY 类型配合 expanding
result = await conn.execute(
    text(DELETE_BY_IDS).bindparams(
        bindparam("ids_list", expanding=True, type_=ARRAY(SQLTYPE_UUID)),
    ),
    {"ids_list": memory_ids}
)
```

### 类型检查工具建议

1. **mypy**：使用 `mypy` 进行静态类型检查
2. **sqlalchemy-stubs**：安装 SQLAlchemy 类型存根文件
3. **IDE 支持**：配置 VS Code 或 PyCharm 的类型检查

```bash
# 安装类型检查工具
pip install mypy sqlalchemy-stubs
```

## 数据模型设计最佳实践

### 1. 使用 dataclass 定义返回模型

对于查询操作，应当使用独立的 dataclass 来定义返回的数据结构，而不是使用字典。

**设计原则**：
- 为每个数据库表的查询结果定义对应的 dataclass 模型
- 数据模型命名以一个下划线开头
- 数据模型注释中描述该数据模型尽量不应该被其他模块直接存储或长期持有。
- 包含数据库表的所有字段，保持字段名称一致
- 在 dataclass 中包含适当的类型注解和验证逻辑
- 提供辅助函数将数据库行转换为 dataclass 对象

**示例结构**：

```python
@dataclass
class _QueryResultModel:
    """查询结果的数据模型，该数据模型尽量不应该被其他模块直接存储或长期持有"""
    id: UUID
    field_name_1: str
    field_name_2: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self):
        """数据验证逻辑"""
        if self.field_name_1 and len(self.field_name_1) > 100:
            raise ValueError("field_name_1 length exceeds limit")

def _row_to_model(row) -> _QueryResultModel:
    """将数据库行转换为模型对象"""
    return _QueryResultModel(
        id=row.id,
        field_name_1=row.field_name_1,
        field_name_2=row.field_name_2,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at
    )
```

### 2. 查询函数返回类型设计

所有查询函数都应当返回对应的 dataclass 对象或对象列表：

```python
# 单个查询返回 Optional[ModelType]
async def query_by_id(item_id: UUID) -> Optional[_QueryResultModel]:
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_BY_ID), {"id": item_id})
        row = result.first()
        return _row_to_model(row) if row else None

# 批量查询返回 List[ModelType]
async def query_by_condition(condition: str) -> List[_QueryResultModel]:
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_BY_CONDITION), {"condition": condition})
        return [_row_to_model(row) for row in result.fetchall()]
```

### 3. 类型注解的最佳实践

- **移除 `Dict[str, Any]` 导入**：查询结果不使用字典类型
- **添加 `datetime` 导入**：时间戳字段需要正确的类型注解
- **保持 UUID 类型**：继续使用标准的 UUID 类型
- **明确的 Optional 类型**：可空字段正确标注为 Optional[Type]

**导入语句示例**：
```python
from dataclasses import dataclass
from typing import Optional, List  # 移除 Dict, Any
from uuid import UUID
from datetime import datetime      # 新增导入
```

### 4. 优势总结

使用 dataclass 替代字典的主要优势：

1. **类型安全**：编译时类型检查，减少运行时错误
2. **IDE 支持**：更好的代码补全和重构支持
3. **代码可读性**：明确的数据结构和字段定义
4. **数据验证**：在 `__post_init__` 中实现数据校验
5. **维护性**：字段变更时能够及时发现和修复相关代码
