"""
Todo 本地文件系统存储后端

使用本地文件系统存储 Todo 数据，以 JSON 格式持久化。
适合测试环境和需要数据持久化的场景。
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import aiofiles

from .base import TodoStorageBackend


class LocalTodoBackend(TodoStorageBackend):
    """
    本地文件系统 Todo 存储后端

    将 Todo 数据以 JSON 格式存储在本地文件系统中。
    不需要 session_id，可作为共享存储使用。

    数据存储在: {base_path}/todos.json
    """

    def __init__(self, session_id: UUID | None = None, base_path: str = "/tmp/todo_storage"):
        """
        初始化本地文件系统存储后端

        Args:
            session_id: 不使用此参数，保留仅为接口兼容
            base_path: 基础存储路径
        """
        super().__init__(session_id)
        self.base_path = Path(base_path)
        self.todos_file = self.base_path / "todos.json"
        self._lock = asyncio.Lock()

        # 确保目录存在
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def _load_todos(self) -> list[dict[str, Any]]:
        """
        从文件加载所有 Todos

        Returns:
            Todo 列表，如果文件不存在或为空则返回空列表
        """
        if not self.todos_file.exists():
            return []

        async with aiofiles.open(self.todos_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return []
            data = json.loads(content)
            return data.get("todos", [])

    async def _save_todos(self, todos: list[dict[str, Any]]) -> None:
        """
        保存 Todos 到文件（原子写入）

        Args:
            todos: Todo 列表
        """
        content = json.dumps({"todos": todos}, ensure_ascii=False, indent=2)
        await self._atomic_write(self.todos_file, content)

    async def _atomic_write(self, file_path: Path, content: str) -> None:
        """
        原子写入文件

        使用临时文件 + 重命名确保原子性，避免写入过程中断导致数据损坏。

        Args:
            file_path: 目标文件路径
            content: 要写入的内容
        """
        # 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(file_path.parent),
            prefix=f".{file_path.name}.tmp"
        )
        try:
            # 写入临时文件
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            # 原子性重命名
            os.replace(temp_path, str(file_path))
        except Exception:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    async def create_todo(self, todo_data: dict[str, Any]) -> str:
        """
        创建新的 Todo

        Args:
            todo_data: Todo 数据字典

        Returns:
            新创建的 Todo ID
        """
        async with self._lock:
            todos = await self._load_todos()
            todos.append(todo_data)
            await self._save_todos(todos)
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
            todos = await self._load_todos()
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
            return await self._load_todos()

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
            todos = await self._load_todos()
            for i, todo in enumerate(todos):
                if todo["id"] == todo_id:
                    todos[i].update(updates)
                    await self._save_todos(todos)
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
            todos = await self._load_todos()
            for i, todo in enumerate(todos):
                if todo["id"] == todo_id:
                    todos.pop(i)
                    await self._save_todos(todos)
                    return True
            return False
