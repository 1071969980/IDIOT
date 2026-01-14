"""
本地文件系统存储后端实现
直接操作操作系统的文件系统，适合测试环境
"""

import os
import tempfile
from pathlib import Path
from typing import Literal
from uuid import UUID

import aiofiles

from .base import FileOperationsStorageBackend


class LocalFileBackend(FileOperationsStorageBackend):
    """
    本地文件系统存储后端

    直接操作操作系统的文件系统，使用 aiofiles 进行异步文件操作。
    使用临时文件 + 原子重命名确保写入安全性。
    适合测试环境使用。
    """

    def __init__(self, session_id: UUID, base_path: str = "/tmp/file_tools"):
        """
        初始化本地文件存储后端

        Args:
            session_id: 会话 ID
            base_path: 基础路径，默认为 /tmp/file_tools
        """
        super().__init__(session_id)
        self.base_path = Path(base_path) / str(session_id)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, file_path: str) -> Path:
        """
        解析完整路径

        Args:
            file_path: 相对文件路径

        Returns:
            完整的绝对路径
        """
        # 防止路径遍历攻击
        resolved = (self.base_path / file_path).resolve()
        if not str(resolved).startswith(str(self.base_path.resolve())):
            raise ValueError(f"非法路径：{file_path}")
        return resolved

    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None
    ) -> tuple[str, int, int]:
        """读取文件内容"""
        full_path = self._resolve_path(file_path)

        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        if full_path.is_dir():
            raise ValueError(f"'{file_path}' 是一个目录，不是文件")

        async with aiofiles.open(full_path, 'r', encoding='utf-8') as f:
            content = await f.read()

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

        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        if full_path.is_dir():
            raise ValueError(f"'{file_path}' 是一个目录，不是文件")

        # 读取文件
        async with aiofiles.open(full_path, 'r', encoding='utf-8') as f:
            content = await f.read()

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

        # 原子写入
        await self._atomic_write(full_path, updated_content)

        return (True, count, updated_content)

    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        """写入文件内容"""
        full_path = self._resolve_path(file_path)

        # 确保父目录存在
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查文件是否存在
        if full_path.exists() and mode == "create":
            if full_path.is_dir():
                raise ValueError(f"'{file_path}' 是一个目录")
            raise FileExistsError(f"文件已存在：{file_path}")

        # 原子写入
        await self._atomic_write(full_path, content)

        return True

    async def _atomic_write(self, file_path: Path, content: str) -> None:
        """
        原子性写入文件

        Args:
            file_path: 文件路径
            content: 文件内容
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

    async def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        full_path = self._resolve_path(file_path)
        return full_path.exists() and full_path.is_file()

    async def delete_file(self, file_path: str) -> bool:
        """删除文件"""
        full_path = self._resolve_path(file_path)

        if not full_path.exists():
            return False

        if full_path.is_dir():
            raise ValueError(f"'{file_path}' 是一个目录，不能删除")

        full_path.unlink()
        return True

    async def list_directory(
        self,
        directory_path: str = "."
    ) -> list[str]:
        """列出目录内容"""
        full_path = self._resolve_path(directory_path)

        if not full_path.exists() or not full_path.is_dir():
            return []

        return sorted([
            item.name for item in full_path.iterdir()
            if not item.name.startswith(".")
        ])
