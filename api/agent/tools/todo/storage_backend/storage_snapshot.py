"""
基于 u2a_session_task.storage_snapshot 的 Todo 存储后端实现

将 Todo 数据存储在 u2a_session_task.storage_snapshot JSONB 字段中，
通过 get_or_create_pending_task 动态解析最新的 pending task，
确保始终在 pending 状态的 task 上进行读写。

storage_snapshot 在 pending 状态可写，processing 之后逻辑只读（SQL 层面强制）。
"""

from uuid import UUID
from typing import Any

from .base import TodoStorageBackend
from ..todo_model import TodoModel

from api.chat.sql_stat.u2a_session_task.utils import (
    update_task_storage_snapshot,
    get_task,
)
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    get_or_create_pending_task,
)
from api.redis.distributed_lock import RedisDistributedLock
from api.redis.lock_names import LockNames


class StorageSnapshotTodoBackend(TodoStorageBackend):
    """
    使用 u2a_session_task.storage_snapshot 的 Todo 存储后端

    每次操作前动态解析最新 pending task，确保始终在 pending task 上读写。
    数据结构：
    {
      "todos": [
        {
          "title": "...",
          "status": "...",
          ...
        }
      ]
    }
    """

    STORAGE_KEY = "todos"

    def __init__(self, session_id: UUID, branch_name: str, user_id: UUID):
        """
        初始化 Storage Snapshot 后端

        Args:
            session_id: 会话 ID
            branch_name: 分支名称
            user_id: 用户 ID（用于 get_or_create_pending_task）
        """
        super().__init__(session_id=session_id)
        self.branch_name = branch_name
        self.user_id = user_id

    async def _resolve_task_id(self) -> UUID:
        """
        动态解析当前分支上最新的 pending task_id

        通过 get_or_create_pending_task 保证返回一个 status=pending 的 task，
        该 task 一定拥有 storage_snapshot（继承自祖先或为空 dict）。

        Returns:
            最新 pending task 的 UUID
        """
        assert self.session_id is not None  # 由构造函数保证
        task_id, _ = await get_or_create_pending_task(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
        )
        return task_id

    async def _get_snapshot(self, task_id: UUID) -> dict[str, Any]:
        """
        获取指定 task 的 storage_snapshot

        Args:
            task_id: 任务 ID

        Returns:
            storage_snapshot 字典

        Raises:
            Exception: 任务不存在或无 storage_snapshot 时抛出
        """
        task = await get_task(task_id)
        if task is None:
            raise Exception(f"Task {task_id} not found")
        if task.storage_snapshot is None:
            raise Exception(f"Task {task_id} has no storage_snapshot")
        return task.storage_snapshot

    async def _save_snapshot(self, task_id: UUID, snapshot: dict[str, Any]) -> None:
        """
        保存 storage_snapshot 到指定 task

        仅当 task 状态为 pending 时才会成功（SQL 层面强制），否则抛出异常。

        Args:
            task_id: 任务 ID
            snapshot: 要保存的快照数据

        Raises:
            ValueError: task 不存在或非 pending 状态
        """
        await update_task_storage_snapshot(task_id, snapshot)

    async def create_todo(self, todo: TodoModel) -> str:
        task_id = await self._resolve_task_id()
        lock_key = LockNames.task_storage_snapshot(task_id)
        async with RedisDistributedLock(lock_key):
            return await self._create_todo_locked(task_id, todo)

    async def _create_todo_locked(self, task_id: UUID, todo: TodoModel) -> str:
        snapshot = await self._get_snapshot(task_id)
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            todos = []

        for existing_todo in todos:
            if existing_todo.get("title") == todo.title:
                raise Exception(f"Todo with title '{todo.title}' already exists")

        todos.append(todo.model_dump())
        snapshot[self.STORAGE_KEY] = todos

        await self._save_snapshot(task_id, snapshot)

        return todo.title

    async def get_todo(self, title: str) -> TodoModel | None:
        task_id = await self._resolve_task_id()
        snapshot = await self._get_snapshot(task_id)
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            return None

        for todo_dict in todos:
            if todo_dict.get("title") == title:
                return TodoModel(**todo_dict)

        return None

    async def get_all_todos(self) -> list[TodoModel]:
        task_id = await self._resolve_task_id()
        snapshot = await self._get_snapshot(task_id)
        todos_dict = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos_dict, list):
            return []

        return [TodoModel(**todo_dict) for todo_dict in todos_dict]

    async def update_todo(self, title: str, updates: dict[str, Any]) -> bool:
        task_id = await self._resolve_task_id()
        lock_key = LockNames.task_storage_snapshot(task_id)
        async with RedisDistributedLock(lock_key):
            return await self._update_todo_locked(task_id, title, updates)

    async def _update_todo_locked(self, task_id: UUID, title: str, updates: dict[str, Any]) -> bool:
        snapshot = await self._get_snapshot(task_id)
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            return False

        for i, todo_dict in enumerate(todos):
            if todo_dict.get("title") == title:
                updated_todo = {**todo_dict, **updates}
                TodoModel(**updated_todo)
                todos[i] = updated_todo
                snapshot[self.STORAGE_KEY] = todos

                await self._save_snapshot(task_id, snapshot)

                return True

        return False

    async def delete_todo(self, title: str) -> bool:
        task_id = await self._resolve_task_id()
        lock_key = LockNames.task_storage_snapshot(task_id)
        async with RedisDistributedLock(lock_key):
            return await self._delete_todo_locked(task_id, title)

    async def _delete_todo_locked(self, task_id: UUID, title: str) -> bool:
        snapshot = await self._get_snapshot(task_id)
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            return False

        original_length = len(todos)
        todos = [todo for todo in todos if todo.get("title") != title]

        if len(todos) == original_length:
            return False

        snapshot[self.STORAGE_KEY] = todos
        await self._save_snapshot(task_id, snapshot)

        return True

    async def title_exists(self, title: str) -> bool:
        todo = await self.get_todo(title)
        return todo is not None

    async def save_all_todos(self, todos: list[TodoModel]) -> None:
        """
        原子性地替换当前任务中的全部 Todo 列表

        在 Redis 分布式锁保护下：读取当前快照 → 替换 todos → 写回。
        """
        task_id = await self._resolve_task_id()
        lock_key = LockNames.task_storage_snapshot(task_id)
        async with RedisDistributedLock(lock_key):
            snapshot = await self._get_snapshot(task_id)
            snapshot[self.STORAGE_KEY] = [t.model_dump(mode="json") for t in todos]
            await self._save_snapshot(task_id, snapshot)
