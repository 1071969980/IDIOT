"""
分布式文件系统 Agent Role 存储后端实现
使用 api.user_space.file_system API
"""

from pathlib import Path
from uuid import UUID

from api.user_space.file_system.path_utils import build_full_path
from api.user_space.file_system.fs_utils.open import open_file
from api.user_space.file_system.fs_utils.list import list_directory_contents

from .base import AgentRoleStorageBackend


class DistributedAgentRoleBackend(AgentRoleStorageBackend):
    """
    分布式文件系统存储后端

    使用现有的 api.user_space.file_system API 提供分布式文件存储。
    这是默认的存储后端，保持与现有代码的向后兼容性。
    """

    def _get_role_dir(self, role_name: str) -> Path:
        """获取角色目录路径"""
        return Path(f".agent_role_definitions/{role_name}/")

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
        file_path = self._get_conversation_strategies_path(role_name)
        full_path = build_full_path(self.user_id, file_path)
        return open_file(self.user_id, full_path, mode)

    def open_concluding_guidance(self, role_name: str, mode: str):
        """
        打开总结引导文件

        Args:
            role_name: 角色名称
            mode: 文件打开模式

        Returns:
            异步文件对象上下文管理器
        """
        file_path = self._get_concluding_guidance_path(role_name)
        full_path = build_full_path(self.user_id, file_path)
        return open_file(self.user_id, full_path, mode)

    def open_strategies_update_cache(self, role_name: str, mode: str):
        """
        打开更新缓存文件

        Args:
            role_name: 角色名称
            mode: 文件打开模式

        Returns:
            异步文件对象上下文管理器
        """
        file_path = self._get_update_cache_path(role_name)
        full_path = build_full_path(self.user_id, file_path)
        return open_file(self.user_id, full_path, mode)

    async def list_roles(self) -> list[str]:
        """
        列出所有角色名称

        Returns:
            角色名称列表，按字母顺序排序
        """
        agent_roles_dir = Path(".agent_role_definitions")
        items = await list_directory_contents(
            user_id=self.user_id,
            directory_path=agent_roles_dir,
            allow_hidden_path_part=True
        )
        role_names = [
            Path(item.file_path).name
            for item in items
            if item.item_type == "folder"
        ]
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
