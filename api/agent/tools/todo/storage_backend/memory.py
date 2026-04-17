"""
基于内存的 Todo 存储后端实现
"""

import asyncio
from uuid import UUID
from typing import Any

from .base import TodoStorageBackend
from ..todo_model import TodoModel


class MemoryTodoBackend(TodoStorageBackend):
    """
    使用内存存储的 Todo 存储后端

    将 Todo 数据存储在内存字典中。
    数据结构：
    {
        "session_id": {
            "todos": [
                {
                    "title": "...",
                    "status": "...",
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

    async def create_todo(self, todo: TodoModel) -> str:
        """
        创建新的 Todo

        Args:
            todo: Todo 数据模型

        Returns:
            新创建的 Todo title

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

            # 4. 检查 title 是否已存在
            for existing_todo in todos:
                if existing_todo.get("title") == todo.title:
                    raise Exception(f"Todo with title '{todo.title}' already exists")

            # 5. 存储 dict（保持兼容）
            todos.append(todo.model_dump())
            session_storage[self.STORAGE_KEY] = todos

            return todo.title

    async def get_todo(self, title: str) -> TodoModel | None:
        """
        获取单个 Todo

        Args:
            title: Todo 标题

        Returns:
            Todo 数据模型，如果不存在返回 None
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

            # 3. 查找指定 title 的 todo
            for todo_dict in todos:
                if todo_dict.get("title") == title:
                    # 转换为 TodoModel
                    return TodoModel(**todo_dict)

            return None

    async def get_all_todos(self) -> list[TodoModel]:
        """
        获取所有 Todos

        Returns:
            Todo 数据模型列表
        """
        async with self._lock:
            # 1. 获取 session 存储
            session_key = self._get_session_key()
            session_storage = self._memory_store.get(session_key)
            if session_storage is None:
                return []

            # 2. 获取 todos 列表
            todos_dict = session_storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos_dict, list):
                return []

            # 3. 转换为 TodoModel 列表
            return [TodoModel(**todo_dict) for todo_dict in todos_dict]

    async def update_todo(self, title: str, updates: dict[str, Any]) -> bool:
        """
        更新 Todo

        Args:
            title: Todo 标题
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
            for i, todo_dict in enumerate(todos):
                if todo_dict.get("title") == title:
                    # 合并更新
                    updated_todo = {**todo_dict, **updates}
                    # 验证更新后的数据
                    TodoModel(**updated_todo)
                    todos[i] = updated_todo
                    session_storage[self.STORAGE_KEY] = todos
                    return True

            # Todo 不存在
            return False

    async def delete_todo(self, title: str) -> bool:
        """
        删除 Todo

        Args:
            title: Todo 标题

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
            todos = [todo for todo in todos if todo.get("title") != title]

            if len(todos) == original_length:
                # 没有找到要删除的 todo
                return False

            # 4. 更新存储
            session_storage[self.STORAGE_KEY] = todos
            return True

    async def title_exists(self, title: str) -> bool:
        """
        检查 title 是否已存在

        Args:
            title: Todo 标题

        Returns:
            如果 title 已存在返回 True，否则返回 False
        """
        todo = await self.get_todo(title)
        return todo is not None

    async def save_all_todos(self, todos: list[TodoModel]) -> None:
        raise NotImplementedError
