---
文档标题：开发上下文 - 存储机制与依赖注入
文档描述：描述 Session Storage 机制、依赖注入和 kwargs 处理、工具工厂和注册机制，以及三层架构分层设计。
文档编辑规范:
- 每个文档应该控制在300到400行,如果超过400行,请考虑拆分当前文档为同名文件夹下的多个文档,以章节名为文件名。超过50行的代码示例,请拆分成单独的文件至同名文件夹,用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关,积极编写链接和引用。链接和引用本次开发开发文档之外的文件时,尽量使用相对于项目根目录的相对路径
---

**目录**:
- [Session Storage 机制](#session-storage-机制)
- [依赖注入和 kwargs 处理](#依赖注入和-kwargs-处理)
- [工具工厂和注册机制](#工具工厂和注册机制)
- [架构分层设计](#架构分层设计)
- [相关文件索引](#相关文件索引)

## Session Storage 机制

Session Storage 是项目提供的会话级持久化存储机制，使用 PostgreSQL 数据库的 JSONB 字段存储灵活的键值对数据。

### 数据库表结构

**文件位置**：`/home/gmh/桌面/IDIOT/api/agent/sql_stat/u2a_session_storage/u2a_session_storage.sql`

```sql
CREATE TABLE IF NOT EXISTS u2a_session_storage (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL UNIQUE,
    storage JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE
);

CREATE TRIGGER trigger_update_u2a_session_storage_updated_at
    BEFORE UPDATE ON u2a_session_storage
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### 数据模型

**文件位置**：`/home/gmh/桌面/IDIOT/api/agent/sql_stat/u2a_session_storage/utils.py`

```python
@dataclass
class _U2ASessionStorage:
    """U2A会话存储数据模型，用于保存多轮对话之间的临时状态和变量"""
    id: UUID
    session_id: UUID
    storage: dict[str, Any]  # JSONB 字段，可存储任意 JSON 数据
    created_at: datetime
    updated_at: datetime
```

### 核心操作函数

```python
# 读取会话存储
async def get_session_storage_by_session_id(session_id: UUID) -> _U2ASessionStorage | None

# 更新会话存储（UPSERT 语义）
async def update_session_storage_by_session_id(session_id: UUID, storage: dict[str, Any]) -> bool

# 插入新存储
async def insert_session_storage(storage_data: _U2ASessionStorageCreate) -> UUID

# 删除存储
async def delete_session_storage_by_session_id(session_id: UUID) -> bool
```

### JSONB 数据结构示例

```json
{
  "todos": [
    {
      "id": "uuidv7-string",
      "title": "完成代码审查",
      "description": "审查 PR #123",
      "status": "pending",
      "priority": 1,
      "tags": ["review", "urgent"],
      "created_at": "2025-01-08T10:00:00Z",
      "updated_at": "2025-01-08T10:00:00Z"
    }
  ],
  "other_data": {
    "key": "value"
  }
}
```

### 关键特性

1. **灵活的 JSONB 存储**：支持任意 JSON 结构
2. **UPSERT 操作**：不存在则创建，存在则更新
3. **会话级隔离**：每个 session 有独立的存储空间
4. **级联删除**：session 删除时自动删除存储数据

## 依赖注入和 kwargs 处理

### kwargs 传递模式

项目的工具系统通过 `**kwargs` 传递依赖参数。

#### 标准的 kwargs 提取模式

**文件位置**：`/home/gmh/桌面/IDIOT/api/agent/tools/ask_user/constructor.py`

```python
def construct_tool(
    config: AskUserChoiceConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    # 从 kwargs 中提取必需依赖
    session_task_id: UUID | None = kwargs.get("session_task_id")  # type: ignore
    if session_task_id is None:
        raise ValueError("session_task_id is required")

    tool = AskUserChoiceTool(config, session_task_id)
    return (GENERATION_TOOL_PARAM, tool)
```

**关键特征**：
- 使用 `kwargs.get("key_name")` 提取依赖
- 使用 `# type: ignore` 注释消除 mypy 警告
- 显式的 None 检查和 ValueError 抛出
- 手动类型注解：`SomeType | None = kwargs.get(...)`

### 类型验证模式

对于可选依赖，需要验证类型：

```python
def construct_tool(
    config: YourToolConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    # 提取可选依赖
    storage_backend: TodoStorageBackend | None = kwargs.get("storage_backend")  # type: ignore

    # 类型验证
    if storage_backend is not None and not isinstance(storage_backend, TodoStorageBackend):
        raise TypeError(
            f"storage_backend must be TodoStorageBackend, "
            f"got {type(storage_backend).__name__}"
        )

    tool = YourTool(config, storage_backend)
    return (GENERATION_TOOL_PARAM, tool)
```

### Config 控制行为的模式

项目中使用特殊 config 值来控制不同的初始化路径：

**参考示例**：`/home/gmh/桌面/IDIOT/api/app/chunk/split_factory/factory.py`

```python
async def split_text(text: str, config: SplitConfig) -> list[str]:
    # 根据 config.type 选择不同的处理器
    if config.type == SplitType.separator:
        worker = SeparatorProcessor(text, config)
    elif config.type == SplitType.regex:
        worker = RegexProcessor(text, config)
    elif config.type == SplitType.markdown_block:
        worker = MarkdownSturctProcessor(text, config)
    # ... 更多分支
```

**应用在 TODO 工具**：
```python
class TodoWriteConfig(SessionToolConfigBase):
    storage_backend: Literal["session_storage", "memory", "kwargs_DI"] = "session_storage"

def construct_todo_write(
    config: TodoWriteConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    if config.storage_backend == "session_storage":
        storage_backend = SessionStorageTodoBackend(session_id=...)
    elif config.storage_backend == "memory":
        storage_backend = MemoryTodoBackend(session_id=...)
    elif config.storage_backend == "kwargs_DI":
        storage_backend = kwargs.get("storage_backend")
        # ... 验证逻辑
```

## 工具工厂和注册机制

### ToolFactory 类

**文件位置**：`/home/gmh/桌面/IDIOT/api/agent/tools/tool_factory/tool_factory.py`

```python
class ToolFactory:
    def __init__(self, user_id: UUID, session_id: UUID, session_task_id: UUID):
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id

    async def prerare_tool(
        self,
        tool_name: str,
        config: SessionToolConfigBase
    ) -> tuple[ChatCompletionToolParam, ToolClosure]:
        if tool_name not in TOOL_INIT_FUNCTIONS.keys():
            raise ValueError(f"Tool {tool_name} is not available")

        return TOOL_INIT_FUNCTIONS[tool_name](
            config=config,
            user_id=self.user_id,
            session_id=self.session_id,
            session_task_id=self.session_task_id
        )
```

### CONSTRUCTOR 注册机制

每个工具在其 `constructor.py` 中定义 CONSTRUCTOR 字典：

```python
CONSTRUCTOR = {TOOL_NAME: construct_tool}
```

然后在 **`tool_init_function.py`** 中注册：

**文件位置**：`/home/gmh/桌面/IDIOT/api/agent/tools/tool_factory/tool_init_function.py`

```python
TOOL_INIT_FUNCTIONS: dict[str, Callable[..., tuple[ChatCompletionToolParam, ToolClosure]]] = {
    **A2A_CHAT_TASK_CONSTRUCTOR,
    **ASK_USER_CONSTRUCTOR,
    # 添加更多工具
}
```

### 注册流程

1. 在工具目录的 `constructor.py` 中定义 `CONSTRUCTOR = {TOOL_NAME: construct_tool}`
2. 在 `tool_init_function.py` 中导入并合并到 `TOOL_INIT_FUNCTIONS`
3. `ToolFactory` 通过 `tool_name` 查找并调用对应的 `construct_tool` 函数
4. `construct_tool` 函数负责创建工具实例和其依赖

## 架构分层设计

### 三层架构

TODO 工具采用三层架构设计：

```
┌─────────────────────────────────────────┐
│         Tool Layer (工具层)              │
│  - 参数验证                              │
│  - Action 分发 (create/update/delete)    │
│  - 返回值构造                            │
└────────────────┬────────────────────────┘
                 │ 调用存储后端方法
┌────────────────▼────────────────────────┐
│    Storage Backend Layer (存储后端层)    │
│  - 持有 session_id                       │
│  - 完整 CRUD 操作                        │
│  - 数据转换和验证                        │
└────────────────┬────────────────────────┘
                 │ 读写数据
┌────────────────▼────────────────────────┐
│       Storage Layer (存储层)             │
│  - PostgreSQL (u2a_session_storage)      │
│  - Memory (dict)                         │
│  - 其他存储介质                          │
└─────────────────────────────────────────┘
```

### 职责划分原则

#### 工具层（Tool Layer）职责

1. **参数验证**：使用 Pydantic 验证 LLM 传递的参数
2. **Action 分发**：根据 action 参数路由到不同的处理方法
3. **业务逻辑编排**：调用存储后端的方法，组合业务逻辑
4. **返回值构造**：构造符合 LLM 理解的返回值
5. **错误处理**：捕获异常并转换为友好的错误消息

**不负责**：
- ❌ 数据持久化细节
- ❌ session_id 管理
- ❌ 数据库连接管理

#### 存储后端层（Storage Backend Layer）职责

1. **持有 session_id**：在 `__init__` 时接收并保存 session_id
2. **完整 CRUD 操作**：
   - `create_todo()`：创建新的 todo
   - `get_todo()`：读取单个 todo（用于验证）
   - `get_all_todos()`：读取所有 todos（用于内部逻辑）
   - `update_todo()`：更新 todo
   - `delete_todo()`：删除 todo
3. **数据转换**：在业务对象和存储格式之间转换
4. **与存储层交互**：实际执行数据库或内存操作

**不负责**：
- ❌ 参数验证（由工具层负责）
- ❌ 返回值格式化（由工具层负责）

### 为什么工具层只暴露写操作

1. **职责单一**：工具层专注于处理 LLM 的写操作请求
2. **未来灵活性**：读取功能可能通过其他机制实现（如自动上下文注入）
3. **存储层完整性**：存储后端仍然需要读取功能来支持 update/delete 操作
4. **内部验证需求**：update 和 delete 前需要先验证 todo 是否存在

### session_id 的流向

```
ToolFactory
  ↓ (通过 kwargs 传递)
construct_todo_write(config, session_id=xxx)
  ↓ (注入到存储后端)
StorageBackend(session_id=xxx)
  ↓ (保存在实例中)
self.session_id = session_id
  ↓ (在 CRUD 操作中使用)
storage.create_todo(...)  # 使用 self.session_id
```

**设计优势**：
- ✅ 工具类不需要持有 session_id，职责更简单
- ✅ 存储后端独立管理 session_id，便于测试和复用
- ✅ 支持不同的存储策略（session_storage/memory/自定义）
- ✅ 便于依赖注入（测试时可注入 mock 后端）

## 相关文件索引

### 核心文件
- 工具开发规范：[`docs/for_LLM_dev/实现新的Agent工具.md`](../../../../for_LLM_dev/实现新的Agent工具.md)
- 工具基础定义：[`api/agent/tools/config_data_model.py`](../../../../api/agent/tools/config_data_model.py)
- 工具数据模型：[`api/agent/tools/data_model.py`](../../../../api/agent/tools/data_model.py)
- 工具类型定义：[`api/agent/tools/type.py`](../../../../api/agent/tools/type.py)
- 工具工厂：[`api/agent/tools/tool_factory/tool_factory.py`](../../../../api/agent/tools/tool_factory/tool_factory.py)
- 工具注册：[`api/agent/tools/tool_factory/tool_init_function.py`](../../../../api/agent/tools/tool_factory/tool_init_function.py)

### Session Storage 相关
- SQL 模板：[`api/agent/sql_stat/u2a_session_storage/u2a_session_storage.sql`](../../../../api/agent/sql_stat/u2a_session_storage/u2a_session_storage.sql)
- 操作函数：[`api/agent/sql_stat/u2a_session_storage/utils.py`](../../../../api/agent/sql_stat/u2a_session_storage/utils.py)

### 参考工具实现
- AskUser 工具（简单）：[`api/agent/tools/ask_user/`](../../../../api/agent/tools/ask_user/)
- A2A Chat Task 工具（复杂）：[`api/agent/tools/a2a_chat_task/`](../../../../api/agent/tools/a2a_chat_task/)
- Agent Roles 工具：[`api/agent/tools/agent_roles/`](../../../../api/agent/tools/agent_roles/)

### 协议类参考
- 用户数据库抽象：[`api/authentication/user_db_base.py`](../../../../api/authentication/user_db_base.py)
- 向量数据库抽象：[`api/vector_db/vector_db_base.py`](../../../../api/vector_db/vector_db_base.py)
- 负载均衡策略：[`api/load_balance/load_balance_strategy.py`](../../../../api/load_balance/load_balance_strategy.py)

---

**下一步**：请参考 [`../design/01_requirements_and_concepts.md`](../design/01_requirements_and_concepts.md) 了解 TODO 工具的需求分析和核心概念定义。
