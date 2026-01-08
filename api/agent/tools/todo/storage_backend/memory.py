"""
基于内存的 Todo 存储后端实现
"""

import asyncio
from uuid import UUID
from typing import Any

from .base import TodoStorageBackend


class MemoryTodoBackend(TodoStorageBackend):
    """
    使用内存存储的 Todo 存储后端

    将 Todo 数据存储在内存字典中。
    数据结构：
    {
        "session_id": {
            "todos": [
                {
                    "id": "...",
                    "title": "...",
                    ...
                }
            ]
        }
    }

    注意：
    - 数据存储在内存中，进程重启后丢失
    - 使用 asyncio.Lock 保护并发访问
    - 适合测试和短期使用
    """

    # 类变量：内存存储
    _memory_store: dict[str, dict[str, Any]] = {}

    # 类变量：异步锁（用于保护并发访问）
    _lock: asyncio.Lock = asyncio.Lock()

    # Session Storage 中的固定键名
    STORAGE_KEY = "todos"

    def __init__(self, session_id: UUID):
        """
        初始化 Memory Storage 后端

        Args:
            session_id: 会话 ID
        """
        super().__init__(session_id)

    def _get_session_key(self) -> str:
        """
        获取 session 在内存存储中的键名

        Returns:
            session 键名（字符串格式的 UUID）
        """
        return str(self.session_id)

    async def _ensure_session_exists(self) -> None:
        """
        确保会话在内存存储中存在，如果不存在则创建
        """
        session_key = self._get_session_key()
        if session_key not in self._memory_store:
            self._memory_store[session_key] = {}

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
        async with self._lock:
            # 1. 确保 session 存在
            await self._ensure_session_exists()

            # 2. 获取 session 存储
            session_key = self._get_session_key()
            session_storage = self._memory_store[session_key]

            # 3. 获取 todos 列表
            todos = session_storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                todos = []

            # 4. 追加新的 todo
            todos.append(todo_data)
            session_storage[self.STORAGE_KEY] = todos

            return todo_data["id"]

    async def get_todo(self, todo_id: str) -> dict[str, Any] | None:
        """
        获取单个 Todo

        Args:
            todo_id: Todo ID

        Returns:
            Todo 数据字典，如果不存在返回 None
        """
        async with self._lock:
            # 1. 获取 session 存储
            session_key = self._get_session_key()
            session_storage = self._memory_store.get(session_key)
            if session_storage is None:
                return None

            # 2. 获取 todos 列表
            todos = session_storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                return None

            # 3. 查找指定 ID 的 todo
            for todo in todos:
                if todo.get("id") == todo_id:
                    return todo

            return None

    async def get_all_todos(self) -> list[dict[str, Any]]:
        """
        获取所有 Todos

        Returns:
            Todo 数据字典列表
        """
        async with self._lock:
            # 1. 获取 session 存储
            session_key = self._get_session_key()
            session_storage = self._memory_store.get(session_key)
            if session_storage is None:
                return []

            # 2. 获取 todos 列表
            todos = session_storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                return []

            return todos

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
        async with self._lock:
            # 1. 获取 session 存储
            session_key = self._get_session_key()
            session_storage = self._memory_store.get(session_key)
            if session_storage is None:
                return False

            # 2. 获取 todos 列表
            todos = session_storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                return False

            # 3. 查找并更新 todo
            for i, todo in enumerate(todos):
                if todo.get("id") == todo_id:
                    # 合并更新
                    todos[i] = {**todo, **updates}
                    session_storage[self.STORAGE_KEY] = todos
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
        async with self._lock:
            # 1. 获取 session 存储
            session_key = self._get_session_key()
            session_storage = self._memory_store.get(session_key)
            if session_storage is None:
                return False

            # 2. 获取 todos 列表
            todos = session_storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                return False

            # 3. 查找并删除 todo
            original_length = len(todos)
            todos = [todo for todo in todos if todo.get("id") != todo_id]

            if len(todos) == original_length:
                # 没有找到要删除的 todo
                return False

            # 4. 更新存储
            session_storage[self.STORAGE_KEY] = todos
            return True
