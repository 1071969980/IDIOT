"""
本地文件系统 Agent Role 存储后端实现
使用 asyncio.to_thread 在线程池中执行同步文件操作
"""

import asyncio
from pathlib import Path
from uuid import UUID

from .base import AgentRoleStorageBackend


class _LocalFileWrapper:
    """
    本地文件对象包装器，兼容分布式文件系统的接口

    在 __aenter__ 中获取锁并打开文件，确保并发安全。
    使用 asyncio.to_thread 在线程池中执行同步文件操作，避免阻塞事件循环。
    """

    def __init__(self, file_path: Path, mode: str, lock: asyncio.Lock):
        self._file_path = file_path
        self._mode = mode
        self._lock = lock
        self._file = None

    async def __aenter__(self):
        await self._lock.acquire()
        self._file = await asyncio.to_thread(open, self._file_path, self._mode)
        return self

    async def __aexit__(self, *args):
        await asyncio.to_thread(self._file.close)
        self._lock.release()

    def read(self) -> bytes:
        return self._file.read()

    def write(self, data: bytes):
        return self._file.write(data)

    def seek(self, pos: int):
        return self._file.seek(pos)

    def truncate(self, size: int = 0):
        return self._file.truncate(size)


class LocalAgentRoleBackend(AgentRoleStorageBackend):
    """
    本地文件系统存储后端

    使用 asyncio.to_thread 在线程池中执行同步文件操作，避免阻塞事件循环。
    使用 asyncio.Lock 保护并发访问。

    适用于开发、测试环境，不依赖分布式文件系统服务。
    """

    def __init__(self, user_id: UUID, base_path: str = "/tmp/agent_role_storage"):
        super().__init__(user_id)
        self.base_path = Path(base_path)
        self.roles_dir = self.base_path / "agent_roles"
        self._lock = asyncio.Lock()
        self.roles_dir.mkdir(parents=True, exist_ok=True)

    def _get_role_dir(self, role_name: str) -> Path:
        """获取角色目录路径"""
        return self.roles_dir / role_name

    def _get_conversation_strategies_path(self, role_name: str) -> Path:
        """获取对话策略文件路径"""
        return self._get_role_dir(role_name) / "conversation_strategies.md"

    def _get_concluding_guidance_path(self, role_name: str) -> Path:
        """获取总结引导文件路径"""
        return self._get_role_dir(role_name) / "concluding_guidance.md"

    def _get_update_cache_path(self, role_name: str) -> Path:
        """获取更新缓存文件路径"""
        return self._get_role_dir(role_name) / "strategies_update_cache.json"

    def open_conversation_strategies(self, role_name: str, mode: str):
        """
        打开对话策略文件

        Args:
            role_name: 角色名称
            mode: 文件打开模式

        Returns:
            异步文件对象上下文管理器
        """
        self._get_role_dir(role_name).mkdir(parents=True, exist_ok=True)
        file_path = self._get_conversation_strategies_path(role_name)
        return _LocalFileWrapper(file_path, mode + 'b', self._lock)

    def open_concluding_guidance(self, role_name: str, mode: str):
        """
        打开总结引导文件

        Args:
            role_name: 角色名称
            mode: 文件打开模式

        Returns:
            异步文件对象上下文管理器
        """
        self._get_role_dir(role_name).mkdir(parents=True, exist_ok=True)
        file_path = self._get_concluding_guidance_path(role_name)
        return _LocalFileWrapper(file_path, mode + 'b', self._lock)

    def open_strategies_update_cache(self, role_name: str, mode: str):
        """
        打开更新缓存文件

        Args:
            role_name: 角色名称
            mode: 文件打开模式

        Returns:
            异步文件对象上下文管理器
        """
        self._get_role_dir(role_name).mkdir(parents=True, exist_ok=True)
        file_path = self._get_update_cache_path(role_name)
        return _LocalFileWrapper(file_path, mode + 'b', self._lock)

    async def list_roles(self) -> list[str]:
        """
        列出所有角色名称

        Returns:
            角色名称列表，按字母顺序排序
        """
        async with self._lock:
            if not self.roles_dir.exists():
                return []
            role_names = [d.name for d in self.roles_dir.iterdir() if d.is_dir()]
            role_names.sort()
            return role_names

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
        async with self.open_conversation_strategies(role_name, "r+") as f:
            f.seek(0)
            f.truncate(0)
            f.write(conversation_strategies.encode("utf-8"))
        async with self.open_concluding_guidance(role_name, "r+") as f:
            f.seek(0)
            f.truncate(0)
            f.write(concluding_guidance.encode("utf-8"))
        async with self.open_strategies_update_cache(role_name, "r+") as f:
            f.seek(0)
            f.truncate(0)
            f.write("{}".encode("utf-8"))
