"""
Agent Role 存储后端抽象基类
定义所有存储后端必须实现的接口
"""

from typing import Union,TYPE_CHECKING
from abc import ABC, abstractmethod
from uuid import UUID
if TYPE_CHECKING:
    from .local import _LocalFileWrapper
    from api.user_space.file_system.fs_utils.file_object import HybridFileObject 


class AgentRoleStorageBackend(ABC):
    """
    Agent Role 存储后端抽象基类

    所有 Agent Role 存储后端都必须继承此类并实现所有抽象方法。
    接口返回异步上下文管理器，支持 `async with` 语法。
    """

    def __init__(self, user_id: UUID):
        """
        初始化存储后端

        Args:
            user_id: 用户 ID
        """
        self.user_id = user_id

    @abstractmethod
    def open_conversation_strategies(self, role_name: str, mode: str) -> Union["HybridFileObject","_LocalFileWrapper"]:
        """
        打开对话策略文件

        Args:
            role_name: 角色名称
            mode: 文件打开模式（如 "r", "w", "r+" 等）

        Returns:
            异步上下文管理器，支持 `async with` 语法
        """
        pass

    @abstractmethod
    def open_concluding_guidance(self, role_name: str, mode: str) -> Union["HybridFileObject","_LocalFileWrapper"]:
        """
        打开总结引导文件

        Args:
            role_name: 角色名称
            mode: 文件打开模式

        Returns:
            异步上下文管理器，支持 `async with` 语法
        """
        pass

    @abstractmethod
    def open_strategies_update_cache(self, role_name: str, mode: str) -> Union["HybridFileObject","_LocalFileWrapper"]:
        """
        打开策略更新缓存文件

        Args:
            role_name: 角色名称
            mode: 文件打开模式

        Returns:
            异步上下文管理器，支持 `async with` 语法
        """
        pass

    @abstractmethod
    async def list_roles(self) -> list[str]:
        """
        列出所有角色名称

        Returns:
            角色名称列表，按字母顺序排序
        """
        pass

    @abstractmethod
    async def initialize_role(self, role_name: str,
                            conversation_strategies: str,
                            concluding_guidance: str) -> None:
        """
        初始化角色（创建三个文件）

        Args:
            role_name: 角色名称
            conversation_strategies: 默认对话策略内容
            concluding_guidance: 默认总结引导内容
        """
        pass
