"""
基于 u2a_session_task.storage_snapshot 的 Todo 存储后端实现

将 Todo 数据存储在 u2a_session_task.storage_snapshot JSONB 字段中，
按任务节点隔离，沿树结构继承祖先快照。
"""

from uuid import UUID
from typing import Any

from .base import TodoStorageBackend
from ..todo_model import TodoModel

from api.chat.sql_stat.u2a_session_task.utils import (
    copy_storage_snapshot_from_nearest_ancestor,
    update_task_storage_snapshot,
    get_task,
)


class StorageSnapshotTodoBackend(TodoStorageBackend):
    """
    使用 u2a_session_task.storage_snapshot 的 Todo 存储后端

    每个 task 节点拥有独立的 storage_snapshot，初始化时从最近祖先继承。
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

    def __init__(self, task_id: UUID):
        """
        初始化 Storage Snapshot 后端

        Args:
            task_id: 任务 ID
        """
        super().__init__(session_id=None)
        self.task_id = task_id

    async def _initialize(self) -> None:
        """
        异步初始化：从最近祖先复制 storage_snapshot，若无则创建空快照
        """
        copied = await copy_storage_snapshot_from_nearest_ancestor(self.task_id)
        if not copied:
            await update_task_storage_snapshot(self.task_id, {self.STORAGE_KEY: []})

    async def _get_snapshot(self) -> dict[str, Any]:
        """
        获取当前任务的 storage_snapshot

        Returns:
            storage_snapshot 字典
        """
        task = await get_task(self.task_id)
        if task is None or task.storage_snapshot is None:
            return {self.STORAGE_KEY: []}
        return task.storage_snapshot

    async def _save_snapshot(self, snapshot: dict[str, Any]) -> bool:
        """
        保存 storage_snapshot 到当前任务

        Args:
            snapshot: 要保存的快照数据

        Returns:
            是否保存成功
        """
        return await update_task_storage_snapshot(self.task_id, snapshot)

    async def create_todo(self, todo: TodoModel) -> str:
        snapshot = await self._get_snapshot()
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            todos = []

        for existing_todo in todos:
            if existing_todo.get("title") == todo.title:
                raise Exception(f"Todo with title '{todo.title}' already exists")

        todos.append(todo.model_dump())
        snapshot[self.STORAGE_KEY] = todos

        success = await self._save_snapshot(snapshot)
        if not success:
            raise Exception("Failed to create todo: update storage_snapshot failed")

        return todo.title

    async def get_todo(self, title: str) -> TodoModel | None:
        snapshot = await self._get_snapshot()
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            return None

        for todo_dict in todos:
            if todo_dict.get("title") == title:
                return TodoModel(**todo_dict)

        return None

    async def get_all_todos(self) -> list[TodoModel]:
        snapshot = await self._get_snapshot()
        todos_dict = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos_dict, list):
            return []

        return [TodoModel(**todo_dict) for todo_dict in todos_dict]

    async def update_todo(self, title: str, updates: dict[str, Any]) -> bool:
        snapshot = await self._get_snapshot()
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            return False

        for i, todo_dict in enumerate(todos):
            if todo_dict.get("title") == title:
                updated_todo = {**todo_dict, **updates}
                TodoModel(**updated_todo)
                todos[i] = updated_todo
                snapshot[self.STORAGE_KEY] = todos

                success = await self._save_snapshot(snapshot)
                if not success:
                    raise Exception("Failed to update todo: update storage_snapshot failed")

                return True

        return False

    async def delete_todo(self, title: str) -> bool:
        snapshot = await self._get_snapshot()
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            return False

        original_length = len(todos)
        todos = [todo for todo in todos if todo.get("title") != title]

        if len(todos) == original_length:
            return False

        snapshot[self.STORAGE_KEY] = todos
        success = await self._save_snapshot(snapshot)

        if not success:
            raise Exception("Failed to delete todo: update storage_snapshot failed")

        return True

    async def title_exists(self, title: str) -> bool:
        todo = await self.get_todo(title)
        return todo is not None
