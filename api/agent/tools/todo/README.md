# TODO Write 工具

AI Agent 的 TODO 管理工具，用于在对话过程中创建、更新、删除任务列表，帮助 AI 跟踪任务进度和状态。

## 目录结构

```
todo/
├── __init__.py                 # 模块导出
├── todo_model.py              # Todo 数据模型
├── config_data_model.py       # 配置和参数定义
├── constructor.py             # 工具实现和构造函数
└── storage_backend/           # 存储后端实现
    ├── __init__.py
    ├── base.py                # 抽象基类
    ├── session_storage.py     # PostgreSQL 后端
    ├── memory.py              # 内存后端
    └── local.py               # 本地文件系统后端
```

## 核心设计

### 1. Todo 数据模型

使用 `title` 作为唯一标识符，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | `str` | Todo 标题（唯一标识符） |
| `status` | `Literal` | 状态：`pending` / `in_progress` / `completed` / `cancelled` |
| `priority` | `int` | 优先级，数值越大优先级越高 |
| `created_at` | `str` | 创建时间（ISO 8601 格式） |
| `updated_at` | `str` | 更新时间（ISO 8601 格式） |

### 2. 状态流转

默认启用状态流转验证，合法流转如下：

```
pending      --> in_progress, cancelled
in_progress  --> completed, cancelled
completed    --> (终态)
cancelled    --> (终态)
```

可通过配置 `enforce_status_transitions=False` 关闭验证。

### 3. 存储后端

支持四种存储后端，通过 `storage_backend` 配置选择：

| 后端 | 配置值 | 说明 | 依赖 |
|------|--------|------|------|
| Session Storage | `"session_storage"` | 使用 PostgreSQL `u2a_session_storage` 表 | `session_id` |
| Memory | `"memory"` | 内存存储，进程重启丢失 | `session_id` |
| Local | `"local"` | 本地文件系统 JSON 持久化 | `local_base_path` |
| 依赖注入 | `"kwargs_DI"` | 从外部注入存储后端实例 | `storage_backend` |

### 4. 操作类型

支持三种操作，均支持**单个和批量**模式：

| 操作 | action | 说明 |
|------|--------|------|
| 创建 | `"create"` | 创建新的 Todo |
| 更新 | `"update"` | 更新现有 Todo 的 status/priority |
| 删除 | `"delete"` | 删除 Todo |

## 快速开始

### 基本用法

```python
from api.agent.tools.todo import CONSTRUCTOR, TOOL_NAME
from api.agent.tools.todo.config_data_model import TodoWriteConfig

# 配置工具
config = TodoWriteConfig(
    enabled=True,
    storage_backend="session_storage",
    enforce_status_transitions=True
)

# 构造工具实例（需要 session_id）
generation_tool_param, tool = CONSTRUCTOR[TOOL_NAME](
    config=config,
    session_id=session_id  # UUID 类型
)

# 调用工具
result = await tool(
    action="create",
    title="完成代码审查",
    status="pending",
    priority=5
)

print(result.str_content)  # "已创建 Todo：完成代码审查"
```

### 批量操作

```python
# 批量创建
result = await tool(
    action="create",
    title=["任务A", "任务B", "任务C"],
    status="pending",
    priority=1
)

# 批量更新状态
result = await tool(
    action="update",
    title=["任务A", "任务B"],
    status="in_progress"
)

# 批量删除
result = await tool(
    action="delete",
    title=["任务C"]
)
```

### 使用不同存储后端

```python
# Memory 后端
config = TodoWriteConfig(storage_backend="memory")
tool_param, tool = CONSTRUCTOR[TOOL_NAME](
    config=config,
    session_id=session_id
)

# Local 后端
config = TodoWriteConfig(
    storage_backend="local",
    local_base_path="./my_todos"
)
tool_param, tool = CONSTRUCTOR[TOOL_NAME](
    config=config
    # 不需要 session_id
)

# 依赖注入模式
from api.agent.tools.todo.storage_backend import TodoStorageBackend

custom_backend = CustomTodoBackend()  # 自定义实现
config = TodoWriteConfig(storage_backend="kwargs_DI")
tool_param, tool = CONSTRUCTOR[TOOL_NAME](
    config=config,
    storage_backend=custom_backend
)
```

## API 参考

### TodoWriteConfig

工具配置类，继承自 `SessionToolConfigBase`。

```python
class TodoWriteConfig:
    enabled: bool = True
    storage_backend: Literal[
        "session_storage",
        "memory",
        "local",
        "kwargs_DI"
    ] = "session_storage"
    local_base_path: str | None = None
    enforce_status_transitions: bool = True
```

### TodoWriteParamDefine

LLM 调用参数定义。

```python
class TodoWriteParamDefine:
    action: Literal["create", "update", "delete"]
    title: str | list[str]
    status: Literal["pending", "in_progress", "completed", "cancelled"] | None
    priority: int | None
```

### TodoWriteTool

工具主类，实现 CRUD 操作。

```python
class TodoWriteTool:
    async def __call__(**kwargs) -> ToolTaskResult
```

### TodoStorageBackend

存储后端抽象基类。

```python
class TodoStorageBackend(ABC):
    @abstractmethod
    async def create_todo(self, todo: TodoModel) -> str: ...

    @abstractmethod
    async def get_todo(self, title: str) -> TodoModel | None: ...

    @abstractmethod
    async def get_all_todos(self) -> list[TodoModel]: ...

    @abstractmethod
    async def update_todo(self, title: str, updates: dict) -> bool: ...

    @abstractmethod
    async def delete_todo(self, title: str) -> bool: ...

    @abstractmethod
    async def title_exists(self, title: str) -> bool: ...
```

## 返回结果

工具调用返回 `ToolTaskResult`，包含：

- `str_content`: 人类可读的结果描述
- `json_content`: 结构化的 JSON 结果（包含详细操作信息）
- `occur_error`: 是否发生错误

### 单个操作返回示例

```python
ToolTaskResult(
    str_content="已创建 Todo：完成代码审查",
    json_content={
        "action": "create",
        "title": "完成代码审查",
        "success": True
    },
    occur_error=False
)
```

### 批量操作返回示例

```python
ToolTaskResult(
    str_content="""批量创建操作完成：
  总数：3
  成功：2
  失败：1

失败详情：
  - 已存在任务: Todo '已存在任务' 已存在""",
    json_content={
        "action": "create",
        "total_count": 3,
        "success_count": 2,
        "failure_count": 1,
        "results": [
            {"title": "任务A", "success": True},
            {"title": "任务B", "success": True},
            {"title": "已存在任务", "success": False, "error": "Todo '已存在任务' 已存在"}
        ]
    },
    occur_error=True  # 有失败时为 True
)
```

## 并发安全

所有存储后端都实现了并发安全机制：

- **Session Storage**: 使用 `u2a_session_storage_lock` 分布式锁
- **Memory**: 使用 `asyncio.Lock` 进程内锁
- **Local**: 使用 `asyncio.Lock` + 原子文件写入

## 自定义存储后端

继承 `TodoStorageBackend` 实现自定义存储：

```python
from api.agent.tools.todo.storage_backend.base import TodoStorageBackend
from ..todo_model import TodoModel

class CustomTodoBackend(TodoStorageBackend):
    async def create_todo(self, todo: TodoModel) -> str:
        # 实现创建逻辑
        pass

    async def get_todo(self, title: str) -> TodoModel | None:
        # 实现获取逻辑
        pass

    # ... 实现其他抽象方法
```

## 注意事项

1. **title 唯一性**: 同一会话中 title 必须唯一
2. **时间格式**: 所有时间戳使用 ISO 8601 格式
3. **批量操作**: 批量操作中部分失败不会回滚已成功的操作
4. **状态流转**: 如需允许任意状态流转，设置 `enforce_status_transitions=False`
5. **Local 后端**: 不支持 session 隔离，所有数据存储在同一文件
