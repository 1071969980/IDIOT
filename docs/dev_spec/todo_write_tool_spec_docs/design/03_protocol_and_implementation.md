---
文档标题：概念设计 - 协议与执行逻辑设计
文档描述：描述协议类设计、存储后端实现设计、工具功能定义、执行逻辑设计和依赖注入流程设计。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关,积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [协议类设计](#协议类设计)
- [存储后端实现设计](#存储后端实现设计)
- [工具功能定义](#工具功能定义)
- [执行逻辑设计](#执行逻辑设计)
- [依赖注入流程设计](#依赖注入流程设计)

## 协议类设计

### TodoStorageBackend 抽象基类

```python
from abc import ABC, abstractmethod
from uuid import UUID
from typing import Any

class TodoStorageBackend(ABC):
    """
    Todo 存储后端抽象基类

    定义了 Todo 存储后端必须实现的接口，提供完整的 CRUD 操作。
    """

    def __init__(self, session_id: UUID):
        """
        初始化存储后端

        Args:
            session_id: 会话 ID，用于隔离不同会话的 Todo 数据
        """
        self.session_id = session_id

    @abstractmethod
    async def create_todo(self, todo_data: dict[str, Any]) -> str:
        """
        创建新的 Todo

        Args:
            todo_data: Todo 数据字典，包含 title, description, status 等字段

        Returns:
            新创建的 Todo ID（字符串格式的 UUID）

        Raises:
            Exception: 创建失败时抛出异常
        """
        pass

    @abstractmethod
    async def get_todo(self, todo_id: str) -> dict[str, Any] | None:
        """
        获取单个 Todo

        Args:
            todo_id: Todo ID（字符串格式的 UUID）

        Returns:
            Todo 数据字典，如果不存在返回 None
        """
        pass

    @abstractmethod
    async def get_all_todos(self) -> list[dict[str, Any]]:
        """
        获取所有 Todos

        Returns:
            Todo 数据字典列表，如果没有则返回空列表
        """
        pass

    @abstractmethod
    async def update_todo(self, todo_id: str, updates: dict[str, Any]) -> bool:
        """
        更新 Todo

        Args:
            todo_id: Todo ID（字符串格式的 UUID）
            updates: 要更新的字段字典

        Returns:
            更新成功返回 True，Todo 不存在返回 False
        """
        pass

    @abstractmethod
    async def delete_todo(self, todo_id: str) -> bool:
        """
        删除 Todo

        Args:
            todo_id: Todo ID（字符串格式的 UUID）

        Returns:
            删除成功返回 True，Todo 不存在返回 False
        """
        pass
```

### 为什么存储后端需要读取方法

虽然工具层只暴露写操作（create/update/delete），但存储后端需要提供读取方法，原因如下：

1. **update 操作需要先读取**：更新 Todo 时需要先读取现有数据，然后合并更新
2. **delete 操作需要验证**：删除前需要确认 Todo 是否存在
3. **数据完整性**：存储层应该提供完整的数据操作能力
4. **未来扩展**：将来可能需要添加读取功能到工具层

**设计原则**：
- ✅ 存储后端提供完整 CRUD（职责完整）
- ✅ 工具层只暴露写操作（需求导向）
- ✅ 读取方法用于内部验证和逻辑（不直接暴露给 LLM）

## 存储后端实现设计

### SessionStorageTodoBackend

#### 实现概述

`SessionStorageTodoBackend` 使用项目的 `u2a_session_storage` 机制存储 Todo 数据。

#### 实现要点

1. **依赖现有的 u2a_session_storage 操作函数**：
   - `get_session_storage_by_session_id(session_id)`
   - `update_session_storage_by_session_id(session_id, storage)`

2. **并发安全保护**：
   - 使用 `u2a_session_storage_lock(session_id)` 分布式锁
   - 所有读写操作都在锁保护下执行
   - 防止 Read-Modify-Write 竞争条件导致的数据丢失
   - 锁的粒度为 Session 级别（锁住整个 storage 对象）

3. **锁的语义**：
   - **锁粒度**：Session 级别
   - **并发规则**：
     - 同一 Session 的锁：互斥 ❌
     - 不同 Session 的锁：并发 ✅
   - **超时时间**：30 秒（可配置）
   - **自动续期**：默认启用

4. **并发更新处理**：
   - 在分布式锁保护下读取最新的 storage
   - 修改 todos 列表
   - 写回 storage（使用 UPSERT 语义）

5. **错误处理**：
   - session 不存在时创建新的 storage
   - todos 键不存在时初始化为空数组

### MemoryTodoBackend

#### 实现概述

`MemoryTodoBackend` 使用内存字典存储 Todo 数据，用于测试和临时场景。

#### 实现要点

1. **使用类变量存储数据**：
   ```python
   class MemoryTodoBackend(TodoStorageBackend):
       _memory_store: dict[str, dict[str, Any]] = {}
   ```

2. **线程安全**：
   - 由于是异步环境，需要考虑并发访问
   - 使用 `asyncio.Lock` 保护共享数据

3. **生命周期**：
   - 数据存储在内存中，进程重启后丢失
   - 适合测试和短期使用

### 两种后端的对比

| 特性 | SessionStorageTodoBackend | MemoryTodoBackend |
|------|--------------------------|-------------------|
| 持久化 | ✅ 持久化到数据库 | ❌ 进程重启后丢失 |
| 性能 | 中等（数据库 I/O + Redis 分布式锁） | 高（纯内存操作） |
| 并发安全 | ✅ Redis 分布式锁 + 数据库事务 | asyncio.Lock |
| 使用场景 | 生产环境 | 测试、临时场景 |
| 跨实例共享 | ✅ 多个实例共享数据 | ❌ 单实例数据 |

## 工具功能定义

### 工具名称

```python
TOOL_NAME = "todo_write"
```

### 工具描述

LLM 看到的工具描述：

```
Manage your TODO items in the current conversation. You can create, update, or delete TODOs to track your tasks and progress.
```

### 参数定义

#### TodoWriteParamDefine

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class TodoWriteParamDefine(BaseModel):
    """Todo Write 工具的参数定义"""

    # Action 参数
    action: Literal["create", "update", "delete"] = Field(
        description="The action to perform: 'create', 'update', or 'delete'"
    )

    # Create 操作参数
    title: Optional[str] = Field(
        default=None,
        description="Todo title (required for create)"
    )
    status: Optional[Literal["pending", "in_progress", "completed", "cancelled"]] = Field(
        default=None,
        description="Todo status (optional for all actions)"
    )
    priority: Optional[int] = Field(
        default=None,
        description="Todo priority, higher is more important (optional for all actions)"
    )

    # Update/Delete 操作参数
    todo_id: Optional[str] = Field(
        default=None,
        description="Todo ID to update or delete (required for update/delete)"
    )

    model_config = ConfigDict(extra="allow")
```

## 执行逻辑设计

### 参数验证流程

```python
async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
    # 1. 参数验证
    try:
        param = TodoWriteParamDefine.model_validate(kwargs)
    except ValidationError as e:
        error_msg = "\n".join([error["msg"] for error in e.errors()])
        return ToolTaskResult(
            str_content=f"Invalid parameters:\n{error_msg}",
            occur_error=True
        )

    # 2. 额外的业务逻辑验证
    if param.action == "create" and not param.title:
        return ToolTaskResult(
            str_content="Error: 'title' is required for create action",
            occur_error=True
        )

    if param.action in ["update", "delete"] and not param.todo_id:
        return ToolTaskResult(
            str_content=f"Error: 'todo_id' is required for {param.action} action",
            occur_error=True
        )

    # 3. Action 分发
    ...
```

### Action 分发逻辑

```python
async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
    # ... 参数验证 ...

    # Action 分发
    if param.action == "create":
        return await self._create_todo(param)
    elif param.action == "update":
        return await self._update_todo(param)
    elif param.action == "delete":
        return await self._delete_todo(param)
    else:
        return ToolTaskResult(
            str_content=f"Unknown action: {param.action}",
            occur_error=True
        )
```

### Create 操作逻辑

```python
from uuid import uuid4
from datetime import datetime, timezone

async def _create_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
    """创建新的 Todo"""

    # 1. 构造 todo_data
    todo_id = str(uuid4())  # 生成 UUID v4
    now = datetime.now(timezone.utc).isoformat()

    todo_data = {
        "id": todo_id,
        "title": param.title,
        "status": param.status or "pending",
        "priority": param.priority or 0,
        "created_at": now,
        "updated_at": now
    }

    # 2. 调用存储后端创建
    try:
        created_id = await self.storage_backend.create_todo(todo_data)
    except Exception as e:
        return ToolTaskResult(
            str_content=f"Failed to create todo: {str(e)}",
            occur_error=True
        )

    # 3. 返回成功结果
    return ToolTaskResult(
        str_content=f"Todo created with ID: {created_id}",
        json_content={
            "action": "create",
            "todo_id": created_id,
            "success": True
        },
        occur_error=False
    )
```

### Update 操作逻辑

```python
async def _update_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
    """更新 Todo"""

    # 1. 先验证 Todo 是否存在
    # 类型断言：_validate_parameters 已确保 param.todo_id 不为 None
    todo_id = param.todo_id
    assert todo_id is not None, "todo_id must not be None for update operation"

    existing = await self.storage_backend.get_todo(todo_id)
    if existing is None:
        return ToolTaskResult(
            str_content=f"Todo '{todo_id}' not found",
            occur_error=True
        )

    # 2. 构造更新数据（只包含非 None 的字段）
    updates = {}
    if param.title is not None:
        updates["title"] = param.title
    if param.status is not None:
        # 验证状态流转（如果配置要求）
        if self.config.enforce_status_transitions:
            if not self._is_valid_status_transition(existing["status"], param.status):
                return ToolTaskResult(
                    str_content=f"Invalid status transition: {existing['status']} → {param.status}",
                    occur_error=True
                )
        updates["status"] = param.status
    if param.priority is not None:
        updates["priority"] = param.priority

    # 更新时间戳
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    # 3. 调用存储后端更新
    try:
        success = await self.storage_backend.update_todo(todo_id, updates)
        if not success:
            return ToolTaskResult(
                str_content=f"Failed to update todo '{todo_id}'",
                occur_error=True
            )
    except Exception as e:
        return ToolTaskResult(
            str_content=f"Failed to update todo: {str(e)}",
            occur_error=True
        )

    # 4. 返回成功结果
    return ToolTaskResult(
        str_content=f"Todo '{todo_id}' updated successfully",
        json_content={
            "action": "update",
            "todo_id": todo_id,
            "success": True
        },
        occur_error=False
    )

def _is_valid_status_transition(self, old_status: str, new_status: str) -> bool:
    """验证状态流转是否合法"""
    valid_transitions = {
        "pending": ["in_progress", "cancelled"],
        "in_progress": ["completed", "cancelled"],
        "completed": [],  # 终态
        "cancelled": []   # 终态
    }
    return new_status in valid_transitions.get(old_status, [])
```

### Delete 操作逻辑

```python
async def _delete_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
    """删除 Todo"""

    # 1. 先验证 Todo 是否存在
    # 类型断言：_validate_parameters 已确保 param.todo_id 不为 None
    todo_id = param.todo_id
    assert todo_id is not None, "todo_id must not be None for delete operation"

    existing = await self.storage_backend.get_todo(todo_id)
    if existing is None:
        return ToolTaskResult(
            str_content=f"Todo '{todo_id}' not found",
            occur_error=True
        )

    # 2. 调用存储后端删除
    try:
        success = await self.storage_backend.delete_todo(todo_id)
        if not success:
            return ToolTaskResult(
                str_content=f"Failed to delete todo '{todo_id}'",
                occur_error=True
            )
    except Exception as e:
        return ToolTaskResult(
            str_content=f"Failed to delete todo: {str(e)}",
            occur_error=True
        )

    # 3. 返回成功结果
    return ToolTaskResult(
        str_content=f"Todo '{todo_id}' deleted successfully",
        json_content={
            "action": "delete",
            "todo_id": todo_id,
            "success": True
        },
        occur_error=False
    )
```

## 依赖注入流程设计

### 完整的依赖注入流程

```
┌─────────────────────────────────────────┐
│         ToolFactory                     │
│  - user_id: UUID                        │
│  - session_id: UUID  ←───────┐         │
│  - session_task_id: UUID       │         │
└────────────────┬────────────────┘         │
                 │                          │
                 │ prerare_tool()           │
                 ↓                          │
┌─────────────────────────────────────────┤
│  construct_todo_write(config,            │
│    user_id=...,                          │
│    session_id=...,  ─────────────────────┤
│    session_task_id=...)                  │
│                                          │
│  1. 提取 session_id                      │
│  2. 根据 config.storage_backend 创建后端 │
│     - "session_storage" →                │
│       SessionStorageTodoBackend(session_id) │
│     - "memory" →                         │
│       MemoryTodoBackend(session_id)      │
│     - "kwargs_DI" →                      │
│       kwargs.get("storage_backend")      │
│  3. 创建 TodoWriteTool(config, backend)  │
└────────────────┬────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────┐
│  TodoWriteTool                           │
│  - config: TodoWriteConfig               │
│  - storage_backend: TodoStorageBackend   │
│    (已持有 session_id)                   │
└─────────────────────────────────────────┘
```

### construct_todo_write 函数实现

```python
def construct_todo_write(
    config: TodoWriteConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 TodoWriteTool 实例

    Args:
        config: 工具配置
        **kwargs: 依赖参数
            - session_id (UUID, 必需): 用于注入到存储后端
            - storage_backend (TodoStorageBackend, 可选): 当 config.storage_backend="kwargs_DI" 时必需

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """

    # 1. 提取 session_id（必需）
    session_id: UUID | None = kwargs.get("session_id")  # type: ignore
    if session_id is None:
        raise ValueError("session_id is required")

    # 2. 根据 config.storage_backend 创建存储后端
    if config.storage_backend == "session_storage":
        # 模式 1: Session Storage
        from .storage_backend.session_storage import SessionStorageTodoBackend
        storage_backend = SessionStorageTodoBackend(session_id=session_id)

    elif config.storage_backend == "memory":
        # 模式 2: Memory Storage
        from .storage_backend.memory import MemoryTodoBackend
        storage_backend = MemoryTodoBackend(session_id=session_id)

    elif config.storage_backend == "kwargs_DI":
        # 模式 3: 依赖注入
        storage_backend: TodoStorageBackend | None = kwargs.get("storage_backend")  # type: ignore

        if storage_backend is None:
            raise ValueError(
                "storage_backend must be provided in kwargs "
                "when config.storage_backend='kwargs_DI'"
            )

        # 类型验证
        if not isinstance(storage_backend, TodoStorageBackend):
            raise TypeError(
                f"storage_backend must be an instance of TodoStorageBackend, "
                f"got {type(storage_backend).__name__}"
            )

    else:
        # 不应该到达这里（Pydantic 会验证 config.storage_backend）
        raise ValueError(f"Unknown storage_backend type: {config.storage_backend}")

    # 3. 创建工具实例
    tool = TodoWriteTool(config=config, storage_backend=storage_backend)

    # 4. 返回工具定义和闭包
    return (
        TODO_WRITE_GENERATION_TOOL_PARAM,
        tool
    )
```

---

**下一步**：请参考 [`../implementation/01_structure_and_config.md`](../implementation/01_structure_and_config.md) 了解详细的实现细节和代码示例。
