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
    insert_session_storage,
    _U2ASessionStorageCreate,
    u2a_session_storage_lock,
)


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
        获取会话的完整 storage 数据

        Returns:
            storage 字典，如果不存在则返回空字典
        """
        session_storage = await get_session_storage_by_session_id(self.session_id)
        if session_storage is None:
            return {}
        return session_storage.storage

    async def _ensure_storage_exists(self) -> None:
        """
        确保会话 storage 存在，如果不存在则创建
        """
        existing = await get_session_storage_by_session_id(self.session_id)
        if existing is None:
            # 创建新的 storage
            await insert_session_storage(
                _U2ASessionStorageCreate(
                    session_id=self.session_id,
                    storage={}
                )
            )

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
            # 1. 确保 storage 存在
            await self._ensure_storage_exists()

            # 2. 获取当前 storage
            storage = await self._get_storage()

            # 3. 获取 todos 列表（如果不存在则初始化为空列表）
            todos = storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                todos = []

            # 4. 追加新的 todo
            todos.append(todo_data)
            storage[self.STORAGE_KEY] = todos

            # 5. 写回 storage
            success = await update_session_storage_by_session_id(
                self.session_id,
                storage
            )

            if not success:
                raise Exception("Failed to create todo: update storage failed")

            return todo_data["id"]

    async def get_todo(self, todo_id: str) -> dict[str, Any] | None:
        """
        获取单个 Todo

        Args:
            todo_id: Todo ID

        Returns:
            Todo 数据字典，如果不存在返回 None
        """
        # 在分布式锁保护下执行操作
        async with u2a_session_storage_lock(self.session_id):
            # 1. 获取 storage
            storage = await self._get_storage()

            # 2. 获取 todos 列表
            todos = storage.get(self.STORAGE_KEY, [])
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
        # 在分布式锁保护下执行操作
        async with u2a_session_storage_lock(self.session_id):
            # 1. 获取 storage
            storage = await self._get_storage()

            # 2. 获取 todos 列表
            todos = storage.get(self.STORAGE_KEY, [])
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
        # 在分布式锁保护下执行操作
        async with u2a_session_storage_lock(self.session_id):
            # 1. 获取 storage
            storage = await self._get_storage()

            # 2. 获取 todos 列表
            todos = storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                return False

            # 3. 查找并更新 todo
            for i, todo in enumerate(todos):
                if todo.get("id") == todo_id:
                    # 合并更新
                    todos[i] = {**todo, **updates}
                    storage[self.STORAGE_KEY] = todos

                    # 写回 storage
                    success = await update_session_storage_by_session_id(
                        self.session_id,
                        storage
                    )

                    if not success:
                        raise Exception("Failed to update todo: update storage failed")

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
            # 1. 获取 storage
            storage = await self._get_storage()

            # 2. 获取 todos 列表
            todos = storage.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                return False

            # 3. 查找并删除 todo
            original_length = len(todos)
            todos = [todo for todo in todos if todo.get("id") != todo_id]

            if len(todos) == original_length:
                # 没有找到要删除的 todo
                return False

            # 4. 写回 storage
            storage[self.STORAGE_KEY] = todos
            success = await update_session_storage_by_session_id(
                self.session_id,
                storage
            )

            if not success:
                raise Exception("Failed to delete todo: update storage failed")

            return True
