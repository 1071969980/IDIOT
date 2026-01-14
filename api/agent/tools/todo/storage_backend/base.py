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

    def __init__(self, session_id: UUID | None = None):
        """
        初始化存储后端

        Args:
            session_id: 会话 ID，用于隔离不同会话的 Todo 数据
                某些存储后端（如本地文件系统）可能不需要此参数
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
                - status (str): Todo 状态
                - priority (int): 优先级
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
