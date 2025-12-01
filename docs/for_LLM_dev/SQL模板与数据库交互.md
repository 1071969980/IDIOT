
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
SELECT * FROM users WHERE id = :id;

-- Single comment line
INSERT INTO users (name) VALUES (:name);

-- CreateTablesAndIndexes (会被解析为list[str])
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    name VARCHAR(100) NOT NULL
);
--
CREATE INDEX idx_users_name ON users(name);
--
CREATE INDEX idx_users_email ON users(email);
```

**解析结果**：
- `"This is a comment block"` → `"SELECT * FROM users WHERE id = :id;"`
- `"Single comment line"` → `"INSERT INTO users (name) VALUES (:name);"`
- `"CreateTablesAndIndexes"` → `["CREATE TABLE...", "CREATE INDEX idx_users_name...", "CREATE INDEX idx_users_email..."]`

## 文件夹结构

```
api/[module]/sql_stat/[table_name]/
├── TableName.sql         # SQL 语句定义（通常使用 PascalCase 或驼峰命名）
├── utils.py              # 数据访问层和模型
└── __init__.py           # 可选的包初始化文件
```

**命名约定示例**：
- `U2AAgentMsg.sql` - 驼峰命名 + 缩写
- `UserTable.sql` - PascalCase
- `session_tasks.sql` - 下划线命名

## 最简代码示例

**SQL 文件** (`U2AAgentMsg.sql`):
```sql
-- InsertAgentMessage
INSERT INTO u2a_agent_messages (user_id, session_id, sub_seq_index, message_type, content, json_content, status, session_task_id)
VALUES (:user_id, :session_id, :sub_seq_index, :message_type, :content, :json_content, :status, :session_task_id)
RETURNING id;

-- QueryAgentMessageById
SELECT * FROM u2a_agent_messages WHERE id = :id_value;

-- CreateAgentMessagesTable
CREATE TABLE IF NOT EXISTS u2a_agent_messages (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL,
    session_id UUID NOT NULL,
    -- ... 其他字段定义
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_agent_messages_session_id ON u2a_agent_messages (session_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_agent_messages_user_id ON u2a_agent_messages (user_id);
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
sql_file_path = Path(__file__).parent / "U2AAgentMsg.sql"
sql_statements = parse_sql_file(sql_file_path)

INSERT_AGENT_MESSAGE = sql_statements["InsertAgentMessage"]
QUERY_AGENT_MESSAGE_BY_ID = sql_statements["QueryAgentMessageById"]
CREATE_AGENT_MESSAGES_TABLE = sql_statements["CreateAgentMessagesTable"]  # 这是一个list[str]

@dataclass
class _U2AAgentMessageCreate:
    """创建代理消息的数据模型"""
    user_id: UUID
    session_id: UUID
    sub_seq_index: int
    message_type: str
    content: str
    status: str
    json_content: Optional[Dict[str, Any]] = None
    session_task_id: Optional[UUID] = None

async def create_table() -> None:
    """创建表和索引 - 处理list[str]类型的SQL语句"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # CREATE_AGENT_MESSAGES_TABLE 是一个list，需要逐条执行
        for stmt in CREATE_AGENT_MESSAGES_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()

async def insert_agent_message(message_data: _U2AAgentMessageCreate) -> UUID:
    """插入新消息 - 数据库自动生成UUID"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(INSERT_AGENT_MESSAGE), {
            "user_id": message_data.user_id,
            "session_id": message_data.session_id,
            "sub_seq_index": message_data.sub_seq_index,
            "message_type": message_data.message_type,
            "content": message_data.content,
            "json_content": message_data.json_content,
            "status": message_data.status,
            "session_task_id": message_data.session_task_id,
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
-- InsertAgentMessagesBatch
INSERT INTO u2a_agent_messages (user_id, session_id, sub_seq_index, message_type, content, json_content, status, session_task_id)
SELECT
    unnest(:user_ids_list) as user_id,
    unnest(:session_ids_list) as session_id,
    unnest(:sub_seq_indices_list) as sub_seq_index,
    unnest(:message_types_list) as message_type,
    unnest(:contents_list) as content,
    unnest(:json_contents_list) as json_content,
    unnest(:statuses_list) as status,
    unnest(:session_task_ids_list) as session_task_id
RETURNING id;

-- UpdateAgentMessageStatusByIds
UPDATE u2a_agent_messages
SET status = :status_value
WHERE id IN :ids_list;
```

**Python 实现**：
```python
@dataclass
class _U2AAgentMessageBatchCreate:
    user_ids: list[UUID]
    session_ids: list[UUID]
    sub_seq_indices: list[int]
    message_types: list[str]
    contents: list[str]
    json_contents: list[Optional[Dict[str, Any]]]
    statuses: list[str]
    session_task_ids: list[Optional[UUID]]

async def insert_agent_messages_batch(messages_data: _U2AAgentMessageBatchCreate) -> list[UUID]:
    """批量插入消息"""
    # 验证所有列表长度一致
    list_lengths = [len(messages_data.user_ids), len(messages_data.session_ids), ...]
    if len(set(list_lengths)) != 1:
        raise ValueError("All input lists must have the same length")

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_AGENT_MESSAGES_BATCH).bindparams(
                bindparam("user_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("session_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                # ... 其他参数类型定义
            ),
            {
                "user_ids_list": messages_data.user_ids,
                "session_ids_list": messages_data.session_ids,
                # ... 其他参数值
            }
        )
        await conn.commit()
        return [row[0] for row in result.fetchall()]

async def update_agent_message_status_by_ids(
    message_ids: list[UUID],
    new_status: str
) -> int:
    """批量更新状态"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_AGENT_MESSAGE_STATUS_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {"status_value": new_status, "ids_list": message_ids}
        )
        await conn.commit()
        return result.rowcount
```

### 2. 动态字段查询

**SQL 定义**：
```sql
-- QueryAgentMessageField1
SELECT :field_name_1 FROM u2a_agent_messages WHERE id = :id_value;

-- QueryAgentMessageField2
SELECT :field_name_1, :field_name_2 FROM u2a_agent_messages WHERE id = :id_value;

-- UpdateAgentMessage1
UPDATE u2a_agent_messages SET :field_name_1 = :field_value_1 WHERE id = :id_value;
```

**Python 实现**：
```python
async def get_agent_message_fields(
    message_id: UUID,
    field_names: list[str]
) -> Optional[Dict[str, Any]]:
    """动态查询指定字段"""
    field_count = len(field_names)

    # 根据字段数量选择SQL模板
    if field_count == 1:
        sql = QUERY_AGENT_MESSAGE_FIELD_1
    elif field_count == 2:
        sql = QUERY_AGENT_MESSAGE_FIELD_2
    # ... 更多字段支持

    # 动态替换字段名占位符
    params = {"id_value": message_id}
    for i, field_name in enumerate(field_names, 1):
        sql = sql.replace(f":field_name_{i}", field_name)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}

async def update_agent_message_fields(
    update_data: _U2AAgentMessageUpdate
) -> bool:
    """动态更新指定字段"""
    field_count = len(update_data.fields)

    # 根据字段数量选择SQL模板
    if field_count == 1:
        sql = UPDATE_AGENT_MESSAGE_1
    elif field_count == 2:
        sql = UPDATE_AGENT_MESSAGE_2
    # ... 更多字段支持

    # 动态替换字段名和值
    params = {"id_value": update_data.message_id}
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
-- CreateAgentMessageTriggers
CREATE OR REPLACE FUNCTION u2a_agent_msg_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER u2a_agent_msg_before_update
BEFORE UPDATE ON u2a_agent_messages
FOR EACH ROW
EXECUTE FUNCTION u2a_agent_msg_update_timestamp();
```

**Python 实现**：
```python
async def create_table() -> None:
    """创建表和所有相关数据库对象"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # 创建表和索引
        for stmt in CREATE_AGENT_MESSAGES_TABLE:
            await conn.execute(text(stmt))

        # 创建触发器和函数
        for stmt in CREATE_AGENT_MESSAGE_TRIGGERS:
            await conn.execute(text(stmt))

        await conn.commit()
```

## 数据库初始化时机

在导入相关模块时，会出发数据库初始化逻辑。

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
INSERT INTO users (name, email)
VALUES (:name, :email)
RETURNING id;
```

```python
# 正确的Python处理
async def create_user(data: UserCreate) -> UUID:
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_USER),
            {"name": data.name, "email": data.email}
        )
        await conn.commit()

        return result.scalar()
```

**错误示例**：
```python
# 错误：Python生成UUID
user_id = uuid4()
await conn.execute(text(INSERT), {"id": user_id, ...})
```