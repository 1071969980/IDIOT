"""
基于 u2a_session_task.storage_snapshot 的 Todo 存储后端实现

将 Todo 数据存储在 u2a_session_task.storage_snapshot JSONB 字段中，
通过 get_branch_storage_snapshot / update_branch_storage_snapshot 动态解析最新的 pending task，
确保始终在 pending 状态的 task 上进行读写。

storage_snapshot 在 pending 状态可写，processing 之后逻辑只读（SQL 层面强制）。
"""

from uuid import UUID
from typing import Any

from .base import TodoStorageBackend
from ..todo_model import TodoModel

from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    get_branch_storage_snapshot,
    update_branch_storage_snapshot,
)


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

    async def create_todo(self, todo: TodoModel) -> str:
        todo_title = todo.title

        def _create(snapshot: dict[str, Any]) -> bool:
            todos = snapshot.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                todos = []

            for existing_todo in todos:
                if existing_todo.get("title") == todo_title:
                    raise Exception(f"Todo with title '{todo_title}' already exists")

            todos.append(todo.model_dump())
            snapshot[self.STORAGE_KEY] = todos
            return True

        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=_create,
        )
        return todo_title

    async def get_todo(self, title: str) -> TodoModel | None:
        _, snapshot = await get_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
        )
        todos = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos, list):
            return None

        for todo_dict in todos:
            if todo_dict.get("title") == title:
                return TodoModel(**todo_dict)

        return None

    async def get_all_todos(self) -> list[TodoModel]:
        _, snapshot = await get_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
        )
        todos_dict = snapshot.get(self.STORAGE_KEY, [])
        if not isinstance(todos_dict, list):
            return []

        return [TodoModel(**todo_dict) for todo_dict in todos_dict]

    async def update_todo(self, title: str, updates: dict[str, Any]) -> bool:
        found_holder: list[bool] = []

        def _update(snapshot: dict[str, Any]) -> bool:
            todos = snapshot.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                return False

            for i, todo_dict in enumerate(todos):
                if todo_dict.get("title") == title:
                    updated_todo = {**todo_dict, **updates}
                    TodoModel(**updated_todo)
                    todos[i] = updated_todo
                    snapshot[self.STORAGE_KEY] = todos
                    found_holder.append(True)
                    return True
            return False

        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=_update,
        )
        return bool(found_holder)

    async def delete_todo(self, title: str) -> bool:
        found_holder: list[bool] = []

        def _delete(snapshot: dict[str, Any]) -> bool:
            todos = snapshot.get(self.STORAGE_KEY, [])
            if not isinstance(todos, list):
                return False

            original_length = len(todos)
            todos = [todo for todo in todos if todo.get("title") != title]

            if len(todos) == original_length:
                return False

            snapshot[self.STORAGE_KEY] = todos
            found_holder.append(True)
            return True

        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=_delete,
        )
        return bool(found_holder)

    async def title_exists(self, title: str) -> bool:
        todo = await self.get_todo(title)
        return todo is not None

    async def save_all_todos(self, todos: list[TodoModel]) -> None:
        """原子性地替换当前任务中的全部 Todo 列表"""
        serialized = [t.model_dump(mode="json") for t in todos]

        def _replace_all(snapshot: dict[str, Any]) -> bool:
            snapshot[self.STORAGE_KEY] = serialized
            return True

        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=_replace_all,
        )
