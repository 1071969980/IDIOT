---
文档标题：实现细节 - 存储后端实现
文档描述：描述存储后端协议类、Session Storage 后端和内存后端的完整实现代码。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用；链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [存储后端协议类实现](#存储后端协议类实现)
- [存储后端具体实现](#存储后端具体实现)

## 存储后端协议类实现

### base.py - TodoStorageBackend ABC

**文件位置**：`api/agent/tools/todo/storage_backend/base.py`

```python
"""
Todo 存储后端抽象基类
定义所有存储后端必须实现的接口
"""

from abc import ABC, abstractmethod
from uuid import UUID
from typing import Any


class TodoStorageBackend(ABC):
    """
    Todo 存储后端抽象基类

    所有 Todo 存储后端都必须继承此类并实现所有抽象方法。
    提供完整的 CRUD 操作：Create, Read, Update, Delete。

    注意：虽然工具层只暴露写操作（create/update/delete），
    但存储后端需要提供读取方法（get_todo, get_all_todos）用于内部验证。
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
            todo_data: Todo 数据字典，必须包含以下字段：
                - id (str): Todo ID（UUID 字符串）
                - title (str): Todo 标题
                - description (str | None): Todo 描述
                - status (str): Todo 状态
                - priority (int): 优先级
                - tags (list[str]): 标签列表
                - created_at (str): 创建时间（ISO 8601）
                - updated_at (str): 更新时间（ISO 8601）

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

        Note:
            此方法用于 update/delete 前验证 Todo 是否存在，
            不直接暴露给 LLM。
        """
        pass

    @abstractmethod
    async def get_all_todos(self) -> list[dict[str, Any]]:
        """
        获取所有 Todos

        Returns:
            Todo 数据字典列表，如果没有则返回空列表

        Note:
            此方法用于内部逻辑（如批量操作），
            不直接暴露给 LLM。
        """
        pass

    @abstractmethod
    async def update_todo(self, todo_id: str, updates: dict[str, Any]) -> bool:
        """
        更新 Todo

        Args:
            todo_id: Todo ID（字符串格式的 UUID）
            updates: 要更新的字段字典，包含要更新的字段和对应的新值

        Returns:
            更新成功返回 True，Todo 不存在返回 False

        Raises:
            Exception: 更新失败时抛出异常
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

        Raises:
            Exception: 删除失败时抛出异常
        """
        pass
```

### 协议类的关键设计点

1. **完整的 CRUD 接口**：即使工具层不暴露 read，存储后端也必须实现
2. **清晰的文档注释**：每个方法都有详细的 Args、Returns、Raises 说明
3. **类型注解完整**：所有参数和返回值都有明确的类型注解
4. **职责边界说明**：通过 Note 注释说明哪些方法不直接暴露给 LLM

## 存储后端具体实现

### session_storage.py - SessionStorageTodoBackend

**文件位置**：`api/agent/tools/todo/storage_backend/session_storage.py`

```python
"""
基于 u2a_session_storage 的 Todo 存储后端实现
"""

from uuid import UUID
from typing import Any

from .base import TodoStorageBackend

# 导入 session storage 操作函数和并发锁
from api.agent.sql_stat.u2a_session_storage.utils import (
    get_session_storage_by_session_id,
    update_session_storage_by_session_id,
    u2a_session_storage_lock,
)

# 注意：u2a_session_storage_lock 使用 Redis 分布式锁保护 Session Storage 的并发访问
# - 锁粒度：Session 级别（锁住整个 storage 对象）
# - 同一 Session 的所有操作串行化
# - 不同 Session 的操作可以并发
# - 默认超时时间：30 秒，自动续期启用
```


class SessionStorageTodoBackend(TodoStorageBackend):
    """
    使用 u2a_session_storage 的 Todo 存储后端

    将 Todo 数据存储在 u2a_session_storage.storage JSONB 字段中。
    数据结构：
    {
      "todos": [
        {
          "id": "...",
          "title": "...",
          ...
        }
      ]
    }
    """

    # Session Storage 中的固定键名
    STORAGE_KEY = "todos"

    def __init__(self, session_id: UUID):
        """
        初始化 Session Storage 后端

        Args:
            session_id: 会话 ID
        """
        super().__init__(session_id)

    async def _get_storage(self) -> dict[str, Any]:
        """
        获取 session storage 数据

        Returns:
            storage 字典，如果不存在则返回空字典
        """
        storage_obj = await get_session_storage_by_session_id(self.session_id)

        if storage_obj is None:
            # Session 不存在，返回空 storage
            return {}

        return storage_obj.storage

    async def _update_storage(self, storage: dict[str, Any]) -> None:
        """
        更新 session storage 数据

        Args:
            storage: 要更新的 storage 字典

        Raises:
            Exception: 更新失败时抛出异常
        """
        success = await update_session_storage_by_session_id(self.session_id, storage)
        if not success:
            raise Exception(f"Failed to update session storage for session {self.session_id}")

    async def create_todo(self, todo_data: dict[str, Any]) -> str:
        """
        创建新的 Todo

        Args:
            todo_data: Todo 数据字典

        Returns:
            新创建的 Todo ID

        Raises:
            Exception: 创建失败时抛出异常
        """
        # 在分布式锁保护下执行操作
        async with u2a_session_storage_lock(self.session_id):
            # 1. 获取现有 storage
            storage = await self._get_storage()

            # 2. 确保 todos 列表存在
            if self.STORAGE_KEY not in storage:
                storage[self.STORAGE_KEY] = []

            # 3. 追加新 todo
            storage[self.STORAGE_KEY].append(todo_data)

            # 4. 写回 storage
            await self._update_storage(storage)

            return todo_data["id"]

    async def get_todo(self, todo_id: str) -> dict[str, Any] | None:
        """
        获取单个 Todo

        Args:
            todo_id: Todo ID

        Returns:
            Todo 数据字典，不存在返回 None
        """
        # 在分布式锁保护下执行操作
        async with u2a_session_storage_lock(self.session_id):
            storage = await self._get_storage()
            todos = storage.get(self.STORAGE_KEY, [])

            # 查找匹配的 todo
            for todo in todos:
                if todo["id"] == todo_id:
                    return todo

            return None

    async def get_all_todos(self) -> list[dict[str, Any]]:
        """
        获取所有 Todos

        Returns:
            Todo 数据字典列表
        """
        # 在分布式锁保护下执行操作
        async with u2a_session_storage_lock(self.session_id):
            storage = await self._get_storage()
            return storage.get(self.STORAGE_KEY, [])

    async def update_todo(self, todo_id: str, updates: dict[str, Any]) -> bool:
        """
        更新 Todo

        Args:
            todo_id: Todo ID
            updates: 要更新的字段字典

        Returns:
            更新成功返回 True，Todo 不存在返回 False

        Raises:
            Exception: 更新失败时抛出异常
        """
        # 在分布式锁保护下执行操作
        async with u2a_session_storage_lock(self.session_id):
            # 1. 获取现有 storage
            storage = await self._get_storage()
            todos = storage.get(self.STORAGE_KEY, [])

            # 2. 查找并更新 todo
            for i, todo in enumerate(todos):
                if todo["id"] == todo_id:
                    # 合并更新
                    todo.update(updates)
                    todos[i] = todo

                    # 写回 storage
                    storage[self.STORAGE_KEY] = todos
                    await self._update_storage(storage)

                    return True

            # Todo 不存在
            return False

    async def delete_todo(self, todo_id: str) -> bool:
        """
        删除 Todo

        Args:
            todo_id: Todo ID

        Returns:
            删除成功返回 True，Todo 不存在返回 False

        Raises:
            Exception: 删除失败时抛出异常
        """
        # 在分布式锁保护下执行操作
        async with u2a_session_storage_lock(self.session_id):
            # 1. 获取现有 storage
            storage = await self._get_storage()
            todos = storage.get(self.STORAGE_KEY, [])

            # 2. 查找并删除 todo
            for i, todo in enumerate(todos):
                if todo["id"] == todo_id:
                    # 删除 todo
                    todos.pop(i)

                    # 写回 storage
                    storage[self.STORAGE_KEY] = todos
                    await self._update_storage(storage)

                    return True

            # Todo 不存在
            return False
```

### memory.py - MemoryTodoBackend

**文件位置**：`api/agent/tools/todo/storage_backend/memory.py`

```python
"""
基于内存的 Todo 存储后端实现
用于测试和临时场景
"""

import asyncio
from uuid import UUID
from typing import Any

from .base import TodoStorageBackend


class MemoryTodoBackend(TodoStorageBackend):
    """
    使用内存存储的 Todo 后端

    数据存储在类级别的字典中，适合测试和临时场景。
    注意：进程重启后数据会丢失。
    """

    # 类级别的内存存储
    # 结构：{session_id (str): {"todos": [...]}}
    _memory_store: dict[str, dict[str, Any]] = {}

    # 异步锁，保护并发访问
    _lock = asyncio.Lock()

    STORAGE_KEY = "todos"

    def __init__(self, session_id: UUID):
        """
        初始化内存后端

        Args:
            session_id: 会话 ID
        """
        super().__init__(session_id)

        # 转换为字符串作为键
        self._session_key = str(session_id)

    async def _get_storage(self) -> dict[str, Any]:
        """
        获取 session 的 storage

        Returns:
            storage 字典，如果不存在则创建空字典
        """
        async with self._lock:
            if self._session_key not in self._memory_store:
                self._memory_store[self._session_key] = {self.STORAGE_KEY: []}

            return self._memory_store[self._session_key]

    async def create_todo(self, todo_data: dict[str, Any]) -> str:
        """
        创建新的 Todo

        Args:
            todo_data: Todo 数据字典

        Returns:
            新创建的 Todo ID
        """
        async with self._lock:
            storage = await self._get_storage()

            if self.STORAGE_KEY not in storage:
                storage[self.STORAGE_KEY] = []

            storage[self.STORAGE_KEY].append(todo_data)

            return todo_data["id"]

    async def get_todo(self, todo_id: str) -> dict[str, Any] | None:
        """
        获取单个 Todo

        Args:
            todo_id: Todo ID

        Returns:
            Todo 数据字典，不存在返回 None
        """
        async with self._lock:
            storage = await self._get_storage()
            todos = storage.get(self.STORAGE_KEY, [])

            for todo in todos:
                if todo["id"] == todo_id:
                    return todo

            return None

    async def get_all_todos(self) -> list[dict[str, Any]]:
        """
        获取所有 Todos

        Returns:
            Todo 数据字典列表
        """
        async with self._lock:
            storage = await self._get_storage()
            return storage.get(self.STORAGE_KEY, []).copy()  # 返回副本

    async def update_todo(self, todo_id: str, updates: dict[str, Any]) -> bool:
        """
        更新 Todo

        Args:
            todo_id: Todo ID
            updates: 要更新的字段字典

        Returns:
            更新成功返回 True，Todo 不存在返回 False
        """
        async with self._lock:
            storage = await self._get_storage()
            todos = storage.get(self.STORAGE_KEY, [])

            for i, todo in enumerate(todos):
                if todo["id"] == todo_id:
                    todo.update(updates)
                    todos[i] = todo
                    return True

            return False

    async def delete_todo(self, todo_id: str) -> bool:
        """
        删除 Todo

        Args:
            todo_id: Todo ID

        Returns:
            删除成功返回 True，Todo 不存在返回 False
        """
        async with self._lock:
            storage = await self._get_storage()
            todos = storage.get(self.STORAGE_KEY, [])

            for i, todo in enumerate(todos):
                if todo["id"] == todo_id:
                    todos.pop(i)
                    return True

            return False

    @classmethod
    def clear_all(cls):
        """
        清空所有存储（用于测试）

        Warning:
            此方法会清空所有 session 的 Todo 数据，仅用于测试！
        """
        cls._memory_store.clear()
```

### 两种实现的对比

| 特性 | SessionStorageTodoBackend | MemoryTodoBackend |
|------|--------------------------|-------------------|
| 持久化 | ✅ PostgreSQL | ❌ 内存 |
| 并发安全 | ✅ Redis 分布式锁 + 数据库事务 | ✅ asyncio.Lock |
| 性能 | 中等（I/O + Redis 锁） | 高（内存） |
| 测试友好 | 中等 | ✅ 高（可清空） |
| 使用场景 | 生产环境 | 测试、开发 |

---

**下一步**：请参考 [`03_tool_and_registration.md`](./03_tool_and_registration.md) 了解工具类实现和工具注册流程。
