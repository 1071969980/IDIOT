"""
内存存储后端实现
使用进程内存存储文件内容，适合测试和短期使用
"""

from asyncio import Lock
from typing import Literal
from uuid import UUID

from .base import FileOperationsStorageBackend, DirectoryItem


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

    async def delete_file(self, file_path: str) -> bool:
        """删除文件"""
        store = await self._get_session_store()

        async with self._lock:
            if file_path in store:
                del store[file_path]
                return True
            return False

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
