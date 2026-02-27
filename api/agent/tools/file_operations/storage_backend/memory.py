"""
内存存储后端实现
使用进程内存存储文件内容，适合测试和短期使用
"""

from asyncio import Lock
from pathlib import Path
from typing import Literal
from uuid import UUID

from .base import FileOperationsStorageBackend, DirectoryItem, OperationResult


class MemoryFileBackend(FileOperationsStorageBackend):
    """
    内存存储后端

    使用类变量在进程内存中存储文件内容，使用 asyncio.Lock 保护并发访问。
    适合单元测试和短期使用场景，进程重启后数据会丢失。
    """

    # 类变量：跨实例共享的内存存储
    _memory_store: dict[str, dict[str, str]] = {}
    _lock: Lock = Lock()

    # 存储结构：
    # {
    #     "session_id_1": {
    #         "file1.txt": "content1",
    #         "dir/file2.txt": "content2"
    #     },
    #     "session_id_2": {
    #         "file3.txt": "content3"
    #     }
    # }

    async def _get_session_store(self) -> dict[str, str]:
        """
        获取当前会话的存储字典

        Returns:
            会话的文件存储字典
        """
        async with self._lock:
            session_key = str(self.session_id)
            if session_key not in self._memory_store:
                self._memory_store[session_key] = {}
            return self._memory_store[session_key]

    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None
    ) -> tuple[str, int, int]:
        """读取文件内容"""
        store = await self._get_session_store()

        if file_path not in store:
            raise FileNotFoundError(f"文件不存在：{file_path}")

        content = store[file_path]
        lines = content.split('\n')
        total_lines = len(lines)

        # 应用 offset
        start = 0 if offset is None else max(0, offset)
        if start >= total_lines:
            return ("", start + 1, total_lines)

        # 应用 limit
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
        store = await self._get_session_store()

        if file_path not in store:
            raise FileNotFoundError(f"文件不存在：{file_path}")

        content = store[file_path]

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

        # 更新存储
        async with self._lock:
            store[file_path] = updated_content

        return (True, count, updated_content)

    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        """写入文件内容"""
        store = await self._get_session_store()

        async with self._lock:
            if file_path in store and mode == "create":
                raise FileExistsError(f"文件已存在：{file_path}")

            # 确保父目录存在（在内存中创建目录条目）
            from pathlib import Path
            parent_dir = str(Path(file_path).parent)
            if parent_dir != ".":
                # 可选：为目录创建标记
                store[f"{parent_dir}/.directory"] = ""

            store[file_path] = content

        return True

    async def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        store = await self._get_session_store()
        return file_path in store

    async def get_item_type(self, path: str) -> Literal["file", "directory"] | None:
        """获取路径对应的项类型"""
        store = await self._get_session_store()

        # 检查是否是文件
        if path in store:
            return "file"

        # 检查是否是目录（有以该路径为前缀的文件，或存在目录标记）
        prefix = path.rstrip("/\\") + "/"
        has_children = any(store_path.startswith(prefix) for store_path in store.keys())
        has_marker = f"{path}/.directory" in store

        if has_children or has_marker:
            return "directory"

        return None

    async def delete_item(self, path: str) -> OperationResult:
        """删除文件或目录"""
        store = await self._get_session_store()

        async with self._lock:
            item_type = await self.get_item_type(path)

            if item_type is None:
                return OperationResult(
                    success=False,
                    item_type="file",
                    source_path=path,
                    message=f"路径不存在：{path}"
                )

            if item_type == "file":
                del store[path]
            else:
                # 删除目录及其所有内容
                prefix = path.rstrip("/\\") + "/"
                keys_to_delete = [k for k in store.keys() if k.startswith(prefix) or k == path]
                for key in keys_to_delete:
                    del store[key]

            return OperationResult(
                success=True,
                item_type=item_type,
                source_path=path,
                message=f"成功删除{'目录' if item_type == 'directory' else '文件'}：{path}"
            )

    async def list_directory(
        self,
        directory_path: str = "."
    ) -> list[DirectoryItem]:
        """列出目录内容"""
        store = await self._get_session_store()
        from pathlib import Path

        result = []

        if directory_path == ".":
            # List root directory - separate files and directories
            seen_entries = set()
            for path in store.keys():
                parts = Path(path).parts
                if parts:
                    entry_name = parts[0]
                    if entry_name not in seen_entries:
                        # Check if this is a directory by looking for child items
                        is_directory = any(store_path.startswith(entry_name + "/") or
                                         store_path.startswith(entry_name + "\\")
                                         for store_path in store.keys())

                        # Also check for directory markers (created when directories are made)
                        has_marker = f"{entry_name}/.directory" in store

                        result.append(DirectoryItem(
                            name=entry_name,
                            type="directory" if (is_directory or has_marker) else "file"
                        ))
                        seen_entries.add(entry_name)
        else:
            # List specific directory
            prefix = directory_path.rstrip("/\\") + "/"
            for path in store.keys():
                if path.startswith(prefix):
                    remaining_path = path[len(prefix):]
                    # Only get the immediate child (first part after the prefix)
                    if "/" in remaining_path:
                        child_name = remaining_path.split("/")[0]
                    elif "\\" in remaining_path:
                        child_name = remaining_path.split("\\")[0]
                    else:
                        child_name = remaining_path

                    if child_name and child_name not in [item.name for item in result]:
                        # Determine if it's a file or directory
                        is_directory = any(store_path.startswith(prefix + child_name + "/") or
                                         store_path.startswith(prefix + child_name + "\\")
                                         for store_path in store.keys())

                        result.append(DirectoryItem(
                            name=child_name,
                            type="directory" if is_directory else "file"
                        ))

        # Sort the result by type (directories first) then by name
        result.sort(key=lambda x: (x.type != "directory", x.name))
        return result

    async def move_item(self, source_path: str, destination_path: str) -> OperationResult:
        """移动文件或目录"""
        store = await self._get_session_store()

        async with self._lock:
            item_type = await self.get_item_type(source_path)

            if item_type is None:
                raise FileNotFoundError(f"路径不存在：{source_path}")

            # 检查目标是否已存在
            dest_type = await self.get_item_type(destination_path)
            if dest_type is not None:
                raise FileExistsError(f"目标路径已存在：{destination_path}")

            # 确保目标父目录存在
            parent_dir = str(Path(destination_path).parent)
            if parent_dir != "." and parent_dir != "":
                store[f"{parent_dir}/.directory"] = ""

            if item_type == "file":
                # 移动文件
                store[destination_path] = store.pop(source_path)
            else:
                # 移动目录及其所有内容
                prefix = source_path.rstrip("/\\") + "/"
                keys_to_move = [k for k in list(store.keys()) if k.startswith(prefix)]

                for key in keys_to_move:
                    relative_path = key[len(prefix):]
                    new_key = f"{destination_path}/{relative_path}"
                    store[new_key] = store.pop(key)

                # 移动目录标记
                marker_key = f"{source_path}/.directory"
                if marker_key in store:
                    del store[marker_key]
                    store[f"{destination_path}/.directory"] = ""

            return OperationResult(
                success=True,
                item_type=item_type,
                source_path=source_path,
                destination_path=destination_path,
                message=f"成功移动{'目录' if item_type == 'directory' else '文件'}：{source_path} -> {destination_path}"
            )

    async def copy_item(self, source_path: str, destination_path: str) -> OperationResult:
        """复制文件或目录"""
        store = await self._get_session_store()

        async with self._lock:
            item_type = await self.get_item_type(source_path)

            if item_type is None:
                raise FileNotFoundError(f"路径不存在：{source_path}")

            # 检查目标是否已存在
            dest_type = await self.get_item_type(destination_path)
            if dest_type is not None:
                raise FileExistsError(f"目标路径已存在：{destination_path}")

            # 确保目标父目录存在
            parent_dir = str(Path(destination_path).parent)
            if parent_dir != "." and parent_dir != "":
                store[f"{parent_dir}/.directory"] = ""

            if item_type == "file":
                # 复制文件
                store[destination_path] = store[source_path]
            else:
                # 复制目录及其所有内容
                prefix = source_path.rstrip("/\\") + "/"
                keys_to_copy = [k for k in store.keys() if k.startswith(prefix)]

                for key in keys_to_copy:
                    relative_path = key[len(prefix):]
                    new_key = f"{destination_path}/{relative_path}"
                    store[new_key] = store[key]

                # 复制目录标记
                store[f"{destination_path}/.directory"] = ""

            return OperationResult(
                success=True,
                item_type=item_type,
                source_path=source_path,
                destination_path=destination_path,
                message=f"成功复制{'目录' if item_type == 'directory' else '文件'}：{source_path} -> {destination_path}"
            )
