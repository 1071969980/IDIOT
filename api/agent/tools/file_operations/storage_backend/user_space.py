"""
用户空间文件系统存储后端实现
集成项目的混合文件系统（S3 + PostgreSQL + Redis）
"""

from pathlib import Path
from typing import Literal
from uuid import UUID

from api.user_space.file_system.fs_utils.open import open_file
from api.user_space.file_system.path_utils import (
    build_full_path,
)
from api.user_space.file_system.sql_stat.utils import (
    query_file_system_items_by_path,
    FileSystemItemType,
)
from api.user_space.file_system.fs_utils.list import _path_contains_hidden_component
from api.user_space.file_system.path_utils import get_user_base_path

from .base import FileOperationsStorageBackend, DirectoryItem


class UserSpaceFileBackend(FileOperationsStorageBackend):
    """
    用户空间文件系统存储后端

    集成项目的混合文件系统（S3 + PostgreSQL + Redis）。
    自动处理分布式锁，支持隐藏文件检测。
    生产环境使用。
    """

    def __init__(self, session_id: UUID, user_id: UUID):
        """
        初始化用户空间文件系统后端

        Args:
            session_id: 会话 ID
            user_id: 用户 ID（必需）

        Raises:
            ValueError: 如果 user_id 未提供
        """
        super().__init__(session_id, user_id)
        if user_id is None:
            raise ValueError("user_id is required for UserSpaceFileBackend")

        self.user_id = user_id
        self.user_base_path = get_user_base_path(user_id)

    def _resolve_path(self, file_path: str) -> Path:
        """
        解析完整路径并检查隐藏组件

        Args:
            file_path: 文件路径

        Returns:
            完整路径

        Raises:
            ValueError: 路径包含隐藏组件
        """
        full_path = build_full_path(self.user_id, Path(file_path))

        # 检查隐藏组件
        if _path_contains_hidden_component(full_path, self.user_base_path):
            raise ValueError(f"路径包含隐藏组件，不允许访问：{file_path}")

        return full_path

    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None
    ) -> tuple[str, int, int]:
        """读取文件内容"""
        full_path = self._resolve_path(file_path)

        # 检查文件是否存在
        file_items = await query_file_system_items_by_path(
            self.user_id,
            str(full_path)
        )
        if not file_items or file_items[0].item_type != FileSystemItemType.FILE:
            raise FileNotFoundError(f"文件不存在：{file_path}")

        # 使用 open_file 读取（自动分布式锁）
        async with open_file(
            user_id=self.user_id,
            file_path=full_path,
            mode='r'
        ) as f:
            content_bytes = f.read()
            content = content_bytes.decode('utf-8')

        lines = content.split('\n')
        total_lines = len(lines)

        # 应用 offset 和 limit
        start = 0 if offset is None else max(0, offset)
        if start >= total_lines:
            return ("", start + 1, total_lines)

        end = total_lines if limit is None else min(total_lines, start + limit)
        selected_lines = lines[start:end]

        return ('\n'.join(selected_lines), start + 1, total_lines)

    async def edit_file(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> tuple[bool, int, str]:
        """编辑文件内容"""
        full_path = self._resolve_path(file_path)

        # 检查文件是否存在
        file_items = await query_file_system_items_by_path(
            self.user_id,
            str(full_path)
        )
        if not file_items or file_items[0].item_type != FileSystemItemType.FILE:
            raise FileNotFoundError(f"文件不存在：{file_path}")

        # 读取内容
        async with open_file(
            user_id=self.user_id,
            file_path=full_path,
            mode='r'
        ) as f:
            content_bytes = f.read()
            content = content_bytes.decode('utf-8')

        # 检查重复
        count = content.count(old_string)
        if count == 0:
            raise ValueError(f"未找到要替换的内容：{old_string}")
        if count > 1 and not replace_all:
            raise ValueError(
                f"内容重复出现{count}次，请设置 replace_all=true"
            )

        # 执行替换
        if replace_all:
            updated_content = content.replace(old_string, new_string)
        else:
            updated_content = content.replace(old_string, new_string, 1)

        # 写回
        async with open_file(
            user_id=self.user_id,
            file_path=full_path,
            mode='r+',
            create_if_missing=False
        ) as f:
            f.truncate(0)
            f.seek(0)
            f.write(updated_content.encode('utf-8'))

        return (True, count, updated_content)

    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        """写入文件内容"""
        full_path = self._resolve_path(file_path)

        # 检查文件是否存在
        file_items = await query_file_system_items_by_path(
            self.user_id,
            str(full_path)
        )
        file_exists = file_items and file_items[0].item_type == FileSystemItemType.FILE

        if file_exists and mode == "create":
            raise FileExistsError(f"文件已存在：{file_path}")

        # 使用 open_file 写入（自动分布式锁）
        create_if_missing = (mode == "create") or not file_exists
        async with open_file(
            user_id=self.user_id,
            file_path=full_path,
            mode='r+',
            create_if_missing=create_if_missing
        ) as f:
            f.truncate(0)
            f.seek(0)
            f.write(content.encode('utf-8'))

        return True

    async def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        try:
            full_path = self._resolve_path(file_path)
        except ValueError:
            # 路径包含隐藏组件，视为不存在
            return False

        file_items = await query_file_system_items_by_path(
            self.user_id,
            str(full_path)
        )
        return bool(file_items and file_items[0].item_type == FileSystemItemType.FILE)

    async def delete_file(self, file_path: str) -> bool:
        """删除文件"""
        from api.user_space.file_system.fs_utils.delete import delete_file_or_folder

        try:
            full_path = self._resolve_path(file_path)
        except ValueError:
            return False

        try:
            await delete_file_or_folder(self.user_id, full_path)
            return True
        except Exception:
            return False

    async def list_directory(
        self,
        directory_path: str = "."
    ) -> list[DirectoryItem]:
        """列出目录内容"""
        from api.user_space.file_system.fs_utils.list import list_directory_contents
        from api.user_space.file_system.sql_stat.utils import FileSystemItemType

        try:
            full_path = self._resolve_path(directory_path)
        except ValueError:
            return []

        try:
            items = await list_directory_contents(
                self.user_id,
                full_path,
                allow_hidden_path_part=False
            )
            # Convert to structured data with name and type using DirectoryItem model
            result = []
            for item in items:
                # Map the internal types ('file', 'folder') to our API types ('file', 'directory')
                item_type = "directory" if item.item_type == FileSystemItemType.FOLDER else "file"
                # Extract just the basename for consistency with other backends
                from pathlib import Path
                name = Path(item.file_path).name
                result.append(DirectoryItem(name=name, type=item_type))
            return result
        except Exception:
            return []
