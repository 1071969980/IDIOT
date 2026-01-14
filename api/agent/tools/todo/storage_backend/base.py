"""
Todo 存储后端抽象基类
定义所有存储后端必须实现的接口
"""

from abc import ABC, abstractmethod
from uuid import UUID
from typing import Any

from ..todo_model import TodoModel


class TodoStorageBackend(ABC):
    """
    Todo 存储后端抽象基类

    所有 Todo 存储后端都必须继承此类并实现所有抽象方法。
    使用 title 作为唯一标识符，支持批量操作。
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
    async def create_todo(self, todo: TodoModel) -> str:
        """
        创建新的 Todo

        Args:
            todo: Todo 数据模型

        Returns:
            新创建的 Todo title

        Raises:
            Exception: 创建失败时抛出异常（如 title 已存在）
        """
        pass

    @abstractmethod
    async def get_todo(self, title: str) -> TodoModel | None:
        """
        获取单个 Todo

        Args:
            title: Todo 标题（唯一标识符）

        Returns:
            Todo 数据模型，如果不存在返回 None

        Note:
            此方法用于 update/delete 前验证 Todo 是否存在，
            不直接暴露给 LLM。
        """
        pass

    @abstractmethod
    async def get_all_todos(self) -> list[TodoModel]:
        """
        获取所有 Todos

        Returns:
            Todo 数据模型列表，如果没有则返回空列表

        Note:
            此方法用于内部逻辑（如批量操作），
            不直接暴露给 LLM。
        """
        pass

    @abstractmethod
    async def update_todo(self, title: str, updates: dict[str, Any]) -> bool:
        """
        更新 Todo

        Args:
            title: Todo 标题（唯一标识符）
            updates: 要更新的字段字典，包含要更新的字段和对应的新值

        Returns:
            更新成功返回 True，Todo 不存在返回 False

        Raises:
            Exception: 更新失败时抛出异常

        Note:
            updates 保持 dict 类型以支持部分更新
        """
        pass

    @abstractmethod
    async def delete_todo(self, title: str) -> bool:
        """
        删除 Todo

        Args:
            title: Todo 标题（唯一标识符）

        Returns:
            删除成功返回 True，Todo 不存在返回 False

        Raises:
            Exception: 删除失败时抛出异常
        """
        pass

    @abstractmethod
    async def title_exists(self, title: str) -> bool:
        """
        检查 title 是否已存在

        Args:
            title: Todo 标题

        Returns:
            如果 title 已存在返回 True，否则返回 False
        """
        pass
