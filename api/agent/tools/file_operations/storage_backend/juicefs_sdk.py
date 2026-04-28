"""
JuiceFS SDK 存储后端实现

通过 JuiceFSWorkerPool 直接操作 JuiceFS 文件系统，实现多租户文件操作。
使用 user_id 派生 meta_url 和 pvc_name，确保租户隔离。
"""

import stat
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

import logfire

from .base import FileOperationsStorageBackend, DirectoryItem, OperationResult
from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.models import FileInfo
from api.juiceFS.path_utils import get_meta_url, get_pvc_name, validate_and_build_path


class JuiceFSSdkBackend(FileOperationsStorageBackend):
    """
    JuiceFS SDK 存储后端

    通过 JuiceFSWorkerPool 直接操作 JuiceFS 文件系统。
    使用 user_id 派生 meta_url，实现多租户隔离。

    Attributes:
        meta_url: JuiceFS 元数据连接 URL
        pvc_name: 用户 PVC 名称（用于路径前缀）
    """

    def __init__(self, session_id: UUID, user_id: UUID, allowed_rel_dirs_in_juicefs_for_tool: list[PurePosixPath] | None = None):
        """
        初始化 JuiceFS SDK 存储后端

        Args:
            session_id: 会话 ID
            user_id: 用户 ID（必需，用于派生 meta_url 和 pvc_name）
            work_dirs: 允许的工作目录列表（默认 [PurePosixPath("/")]，即不做额外限制）

        Raises:
            ValueError: user_id 为 None 时
        """
        super().__init__(session_id, user_id)
        if user_id is None:
            raise ValueError("user_id is required for JuiceFSSdkBackend")

        self.meta_url = get_meta_url(str(user_id))
        self.pvc_name = get_pvc_name(str(user_id))
        self.allowed_rel_dirs_in_juicefs_for_tool = allowed_rel_dirs_in_juicefs_for_tool if allowed_rel_dirs_in_juicefs_for_tool is not None else [PurePosixPath("./")]
        self._pool = None
        
        for rel_dir in self.allowed_rel_dirs_in_juicefs_for_tool:
            if rel_dir.is_absolute():
                raise ValueError("allowed_rel_dirs_in_juicefs_for_tool must be relative paths")

    @property
    def pool(self):
        """
        延迟获取全局 JuiceFSWorkerPool 实例

        Returns:
            JuiceFSWorkerPool: 全局工作进程池实例
        """
        if self._pool is None:
            self._pool = get_worker_pool()
        return self._pool

    def _check_work_dir_access(self, safe_path: str) -> None:
        """
        验证路径是否在允许的工作目录范围内

        Args:
            safe_path: 已验证的安全路径，格式为 /{pvc_name}/...

        Raises:
            ValueError: 路径不在任何允许的工作目录范围内
        """
        pvc_prefix = PurePosixPath(f"/{self.pvc_name}")
        # path_in_pvc = PurePosixPath(safe_path).relative_to(pvc_prefix) or PurePosixPath("/")

        for rel_dir in self.allowed_rel_dirs_in_juicefs_for_tool:
            work_dir = pvc_prefix / rel_dir
            if PurePosixPath(safe_path).is_relative_to(work_dir):
                return

        work_dirs_str = ", ".join(str(d) for d in self.allowed_rel_dirs_in_juicefs_for_tool)
        raise ValueError(f"路径不在允许的工作目录范围内，允许的目录: {work_dirs_str}")

    def _resolve_path(self, file_path: str) -> str:
        """
        构建安全的 JuiceFS 路径并验证工作目录范围

        Args:
            file_path: 用户输入的相对路径

        Returns:
            完整的安全路径，格式为 /{pvc_name}/...

        Raises:
            ValueError: 路径无效、包含非法字符或不在工作目录范围内
        """
        safe_path = validate_and_build_path(file_path, self.pvc_name)
        self._check_work_dir_access(safe_path)
        return safe_path

    # ========== 读取操作 ==========

    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None
    ) -> tuple[str, int, int]:
        """
        读取文件内容

        Args:
            file_path: 文件路径
            offset: 起始行偏移（从0开始）
            limit: 最大读取行数

        Returns:
            (content, first_line_number, total_lines)

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限访问
            ValueError: 路径无效
        """
        safe_path = self._resolve_path(file_path)

        with logfire.span("JuiceFSSdkBackend::read_file", path=safe_path):
            result = await self.pool.call(self.meta_url, Operation.READ, safe_path)

            # bytes -> str
            try:
                content = result.content.decode('utf-8')
            except UnicodeDecodeError as e:
                raise ValueError(f"文件编码错误，无法解码为 UTF-8: {e}")

            lines = content.split('\n')
            total_lines = len(lines)

            # 处理空文件
            if total_lines == 1 and lines[0] == '':
                return ("", 1, 0)

            # 计算起始行
            start = 0 if offset is None else max(0, offset)
            if start >= total_lines:
                return ("", start + 1, total_lines)

            # 计算结束行
            end = total_lines if limit is None else min(total_lines, start + limit)
            selected_lines = lines[start:end]

            return ('\n'.join(selected_lines), start + 1, total_lines)

    # ========== 写入操作 ==========

    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        """
        写入文件内容

        Args:
            file_path: 文件路径
            content: 文件内容
            mode: 写入模式

        Returns:
            True 如果成功

        Raises:
            FileExistsError: 文件已存在且 mode="create"
            PermissionError: 无权限写入
            ValueError: 路径无效
        """
        safe_path = self._resolve_path(file_path)

        # 检查文件是否存在（仅 create 模式）
        if mode == "create":
            exists = await self.file_exists(file_path)
            if exists:
                raise FileExistsError(f"文件已存在：{file_path}")

        with logfire.span("JuiceFSSdkBackend::write_file", path=safe_path):
            data = content.encode('utf-8')
            await self.pool.call(self.meta_url, Operation.WRITE, safe_path, data)
            return True

    # ========== 编辑操作 ==========

    async def edit_file(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> tuple[bool, int, str]:
        """
        编辑文件内容，替换指定字符串

        Args:
            file_path: 文件路径
            old_string: 要替换的字符串
            new_string: 替换后的字符串
            replace_all: 是否替换所有匹配项

        Returns:
            (success, replace_count, updated_content)

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: old_string 不存在或重复出现且 replace_all=False
        """
        # 读取现有内容
        content, _, _ = await self.read_file(file_path)

        # 检查匹配
        count = content.count(old_string)
        if count == 0:
            raise ValueError(f"未找到要替换的内容：{old_string}")
        if count > 1 and not replace_all:
            raise ValueError(f"内容重复出现 {count} 次，请设置 replace_all=true 或指定更精确的内容")

        # 执行替换
        if replace_all:
            updated = content.replace(old_string, new_string)
        else:
            updated = content.replace(old_string, new_string, 1)

        # 写回文件
        await self.write_file(file_path, updated, mode="overwrite")

        return (True, count, updated)

    # ========== 辅助方法 ==========

    async def file_exists(self, file_path: str) -> bool:
        """
        检查文件是否存在

        Args:
            file_path: 文件路径

        Returns:
            True 如果存在
        """
        try:
            safe_path = self._resolve_path(file_path)
        except ValueError:
            return False

        result = await self.pool.call(self.meta_url, Operation.EXISTS, safe_path)
        return result.exists

    async def get_item_type(self, path: str) -> Literal["file", "directory"] | None:
        """
        获取路径对应的项类型

        Args:
            path: 路径

        Returns:
            "file", "directory" 或 None（不存在）
        """
        try:
            safe_path = self._resolve_path(path)
        except ValueError:
            return None

        try:
            # 直接调用 STAT 获取状态，避免重复远程调用
            stat_result = await self.pool.call(self.meta_url, Operation.STAT, safe_path)
            if stat.S_ISDIR(stat_result.stat_info.st_mode):
                return "directory"
            return "file"
        except Exception:
            # 文件不存在或其他错误
            return None

    # ========== 列表操作 ==========

    async def list_directory(self, directory_path: str = ".") -> list[DirectoryItem]:
        """
        列出目录内容

        Args:
            directory_path: 目录路径

        Returns:
            目录项列表
        """
        try:
            safe_path = self._resolve_path(directory_path)
        except ValueError:
            return []

        # detail=True 必须设置，以获取文件类型信息
        result = await self.pool.call(self.meta_url, Operation.LISTDIR, safe_path, True)

        items = []
        for entry in result.entries:
            # detail=True 时返回 FileInfo 对象
            if isinstance(entry, FileInfo):
                item_type = "directory" if stat.S_ISDIR(entry.st_mode) else "file"
                items.append(DirectoryItem(name=entry.name, type=item_type))

        # 排序：目录优先，然后按名称排序
        items.sort(key=lambda x: (x.type != "directory", x.name))
        return items

    # ========== 删除操作 ==========

    async def delete_item(self, path: str) -> OperationResult:
        """
        删除文件或目录

        Args:
            path: 要删除的路径

        Returns:
            操作结果
        """
        item_type = await self.get_item_type(path)
        if item_type is None:
            return OperationResult(
                success=False,
                item_type="file",
                source_path=path,
                message=f"路径不存在：{path}"
            )

        safe_path = self._resolve_path(path)
        await self.pool.call(self.meta_url, Operation.RMR, safe_path)

        type_name = "目录" if item_type == "directory" else "文件"
        return OperationResult(
            success=True,
            item_type=item_type,
            source_path=path,
            message=f"成功删除{type_name}：{path}"
        )

    # ========== 移动操作 ==========

    async def move_item(
        self,
        source_path: str,
        destination_path: str
    ) -> OperationResult:
        """
        移动/重命名文件或目录

        Args:
            source_path: 源路径
            destination_path: 目标路径

        Returns:
            操作结果

        Raises:
            FileNotFoundError: 源路径不存在
            FileExistsError: 目标路径已存在
        """
        item_type = await self.get_item_type(source_path)
        if item_type is None:
            raise FileNotFoundError(f"源路径不存在：{source_path}")

        dest_type = await self.get_item_type(destination_path)
        if dest_type is not None:
            raise FileExistsError(f"目标路径已存在：{destination_path}")

        src_safe = self._resolve_path(source_path)
        dst_safe = self._resolve_path(destination_path)

        await self.pool.call(self.meta_url, Operation.RENAME, src_safe, dst_safe)

        type_name = "目录" if item_type == "directory" else "文件"
        return OperationResult(
            success=True,
            item_type=item_type,
            source_path=source_path,
            destination_path=destination_path,
            message=f"成功移动{type_name}：{source_path} -> {destination_path}"
        )

    # ========== 复制操作 ==========

    async def copy_item(
        self,
        source_path: str,
        destination_path: str
    ) -> OperationResult:
        """
        复制文件或目录

        Args:
            source_path: 源路径
            destination_path: 目标路径

        Returns:
            操作结果

        Raises:
            FileNotFoundError: 源路径不存在
            FileExistsError: 目标路径已存在
        """
        item_type = await self.get_item_type(source_path)
        if item_type is None:
            raise FileNotFoundError(f"源路径不存在：{source_path}")

        dest_type = await self.get_item_type(destination_path)
        if dest_type is not None:
            raise FileExistsError(f"目标路径已存在：{destination_path}")

        src_safe = self._resolve_path(source_path)
        dst_safe = self._resolve_path(destination_path)

        await self.pool.call(self.meta_url, Operation.CLONE, src_safe, dst_safe)

        type_name = "目录" if item_type == "directory" else "文件"
        return OperationResult(
            success=True,
            item_type=item_type,
            source_path=source_path,
            destination_path=destination_path,
            message=f"成功复制{type_name}：{source_path} -> {destination_path}"
        )