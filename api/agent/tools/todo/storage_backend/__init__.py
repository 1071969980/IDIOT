"""
Todo 存储后端模块

提供不同的存储后端实现：
- StorageSnapshotTodoBackend: 使用 u2a_session_task 的 storage_snapshot 字段（默认）
- SessionStorageTodoBackend: 使用 PostgreSQL 的 u2a_session_storage
- MemoryTodoBackend: 使用内存存储
- LocalTodoBackend: 使用本地文件系统（JSON 格式）
"""

from .base import TodoStorageBackend
from .storage_snapshot import StorageSnapshotTodoBackend
from .session_storage import SessionStorageTodoBackend
from .memory import MemoryTodoBackend
from .local import LocalTodoBackend

__all__ = [
    "TodoStorageBackend",
    "StorageSnapshotTodoBackend",
    "SessionStorageTodoBackend",
    "MemoryTodoBackend",
    "LocalTodoBackend"
]
