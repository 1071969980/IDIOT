"""
用户 Pod 文件操作存储后端实现

在用户容器中通过 bash 命令执行文件操作。
"""

import base64
import os
import shlex
from typing import Literal
from uuid import UUID

import logfire

from api.user_pod_command import (
    pod_command_session,
    execute_command,
    CommandResult,
)

from .base import FileOperationsStorageBackend, DirectoryItem, OperationResult


class UserPodFileBackend(FileOperationsStorageBackend):
    """
    用户 Pod 文件操作存储后端

    通过 user_pod_command 模块在用户容器中执行文件操作命令。
    适用于需要在用户运行环境中操作文件的场景。
    """

    def __init__(
        self,
        session_id: UUID,
        user_id: UUID,
        timeout: float = 120.0,
        pod_ready_timeout: float = 300.0,
    ):
        """
        初始化用户 Pod 文件操作后端

        Args:
            session_id: 会话 ID
            user_id: 用户 ID（必需）
            timeout: 单个命令执行超时时间（秒）
            pod_ready_timeout: Pod 就绪等待超时时间（秒）

        Raises:
            ValueError: 如果 user_id 未提供
        """
        super().__init__(session_id, user_id)
        if user_id is None:
            raise ValueError("user_id is required for UserPodFileBackend")

        self.user_id = user_id
        self.timeout = timeout
        self.pod_ready_timeout = pod_ready_timeout

    async def _execute_command(self, command: str) -> CommandResult:
        """
        执行 bash 命令的封装方法

        Args:
            command: 要执行的 bash 命令字符串

        Returns:
            CommandResult: 命令执行结果
        """
        with logfire.span("UserPodFileBackend._execute_command", command=command):
            async with pod_command_session(
                user_id=self.user_id,
                pod_ready_timeout=self.pod_ready_timeout,
            ) as session:
                return await execute_command(
                    pod_command_session_struct=session,
                    command=command,
                    timeout=self.timeout,
                )

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
        """
        escaped_path = shlex.quote(file_path)

        # 先获取总行数
        wc_result = await self._execute_command(f"wc -l < {escaped_path}")
        if wc_result.returncode != 0:
            raise FileNotFoundError(f"文件不存在或无法访问：{file_path}")

        total_lines = 0
        wc_output = wc_result.stdout.strip()
        if wc_output:
            try:
                total_lines = int(wc_output)
            except ValueError:
                total_lines = 0

        # 构建读取命令
        if offset is not None and limit is not None:
            # 使用 tail + head 组合
            cmd = f"tail -n +{offset + 1} {escaped_path} | head -n {limit}"
        elif offset is not None:
            cmd = f"tail -n +{offset + 1} {escaped_path}"
        elif limit is not None:
            cmd = f"head -n {limit} {escaped_path}"
        else:
            cmd = f"cat {escaped_path}"

        result = await self._execute_command(cmd)
        if result.returncode != 0:
            raise FileNotFoundError(f"文件读取失败：{file_path}")

        content = result.stdout
        first_line = (offset or 0) + 1

        return (content, first_line, total_lines)

    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        """
        写入文件内容

        使用 base64 编码避免特殊字符问题。

        Args:
            file_path: 文件路径
            content: 文件内容
            mode: 写入模式

        Returns:
            True 如果成功
        """
        if mode == "create":
            exists = await self.file_exists(file_path)
            if exists:
                raise FileExistsError(f"文件已存在：{file_path}")

        # 创建父目录
        parent = os.path.dirname(file_path)
        if parent:
            mkdir_result = await self._execute_command(f"mkdir -p {shlex.quote(parent)}")
            if mkdir_result.returncode != 0:
                raise PermissionError(f"无法创建目录：{parent}")

        # 使用 base64 编码避免特殊字符问题
        encoded = base64.b64encode(content.encode('utf-8')).decode('ascii')
        escaped_path = shlex.quote(file_path)
        cmd = f"echo {encoded} | base64 -d > {escaped_path}"

        result = await self._execute_command(cmd)
        if result.returncode != 0:
            raise PermissionError(f"文件写入失败：{file_path}")

        return True

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
        """
        # 先读取文件内容
        content, _, _ = await self.read_file(file_path)

        # 检查匹配
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

        # 写回文件
        await self.write_file(file_path, updated_content, mode="overwrite")

        return (True, count, updated_content)

    async def file_exists(self, file_path: str) -> bool:
        """
        检查文件是否存在

        Args:
            file_path: 文件路径

        Returns:
            True 如果文件存在
        """
        escaped = shlex.quote(file_path)
        result = await self._execute_command(f"test -f {escaped}")
        return result.returncode == 0

    async def get_item_type(self, path: str) -> Literal["file", "directory"] | None:
        """
        获取路径对应的项类型

        Args:
            path: 路径

        Returns:
            "file", "directory" 或 None（不存在）
        """
        escaped = shlex.quote(path)

        # 检查是否为文件
        result = await self._execute_command(f"test -f {escaped}")
        if result.returncode == 0:
            return "file"

        # 检查是否为目录
        result = await self._execute_command(f"test -d {escaped}")
        if result.returncode == 0:
            return "directory"

        return None

    async def delete_item(self, path: str) -> OperationResult:
        """
        删除文件或目录

        Args:
            path: 要删除的路径

        Returns:
            OperationResult: 操作结果
        """
        item_type = await self.get_item_type(path)
        if item_type is None:
            return OperationResult(
                success=False,
                item_type="file",
                source_path=path,
                message=f"路径不存在：{path}"
            )

        escaped = shlex.quote(path)
        result = await self._execute_command(f"rm -rf {escaped}")

        success = result.returncode == 0
        type_name = "目录" if item_type == "directory" else "文件"

        return OperationResult(
            success=success,
            item_type=item_type,
            source_path=path,
            message=f"成功删除{type_name}：{path}" if success else f"删除失败：{result.stderr}"
        )

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
            OperationResult: 操作结果
        """
        item_type = await self.get_item_type(source_path)
        if item_type is None:
            raise FileNotFoundError(f"源路径不存在：{source_path}")

        # 创建目标父目录
        dest_parent = os.path.dirname(destination_path)
        if dest_parent:
            await self._execute_command(f"mkdir -p {shlex.quote(dest_parent)}")

        escaped_source = shlex.quote(source_path)
        escaped_dest = shlex.quote(destination_path)
        cmd = f"mv {escaped_source} {escaped_dest}"

        result = await self._execute_command(cmd)
        success = result.returncode == 0
        type_name = "目录" if item_type == "directory" else "文件"

        return OperationResult(
            success=success,
            item_type=item_type,
            source_path=source_path,
            destination_path=destination_path,
            message=f"成功移动{type_name}：{source_path} -> {destination_path}" if success else f"移动失败：{result.stderr}"
        )

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
            OperationResult: 操作结果
        """
        item_type = await self.get_item_type(source_path)
        if item_type is None:
            raise FileNotFoundError(f"源路径不存在：{source_path}")

        # 创建目标父目录
        dest_parent = os.path.dirname(destination_path)
        if dest_parent:
            await self._execute_command(f"mkdir -p {shlex.quote(dest_parent)}")

        escaped_source = shlex.quote(source_path)
        escaped_dest = shlex.quote(destination_path)
        cmd = f"cp -r {escaped_source} {escaped_dest}"

        result = await self._execute_command(cmd)
        success = result.returncode == 0
        type_name = "目录" if item_type == "directory" else "文件"

        return OperationResult(
            success=success,
            item_type=item_type,
            source_path=source_path,
            destination_path=destination_path,
            message=f"成功复制{type_name}：{source_path} -> {destination_path}" if success else f"复制失败：{result.stderr}"
        )

    async def list_directory(
        self,
        directory_path: str = "."
    ) -> list[DirectoryItem]:
        """
        列出目录内容

        Args:
            directory_path: 目录路径

        Returns:
            目录项列表
        """
        escaped = shlex.quote(directory_path)
        # 使用 -A 显示隐藏文件（除了 . 和 ..），-F 添加类型指示符
        cmd = f"ls -A -F {escaped} 2>/dev/null || true"
        result = await self._execute_command(cmd)

        items = []
        output = result.stdout.strip()
        if not output:
            return items

        for line in output.split('\n'):
            if not line:
                continue

            # -F 选项添加的类型指示符：
            # / 表示目录，@ 表示符号链接，* 表示可执行文件，无后缀表示普通文件
            if line.endswith('/'):
                items.append(DirectoryItem(name=line[:-1], type="directory"))
            elif line.endswith('@'):
                # 符号链接，暂时作为文件处理
                items.append(DirectoryItem(name=line[:-1], type="file"))
            elif line.endswith('*'):
                # 可执行文件
                items.append(DirectoryItem(name=line[:-1], type="file"))
            else:
                items.append(DirectoryItem(name=line, type="file"))

        # 排序：目录在前，然后按名称排序
        items.sort(key=lambda x: (x.type != "directory", x.name))

        return items