"""
Todo 存储后端模块

提供存储后端实现：
- StorageSnapshotTodoBackend: 使用 u2a_session_task 的 storage_snapshot 字段（默认）
"""

from .base import TodoStorageBackend
from .storage_snapshot import StorageSnapshotTodoBackend

__all__ = [
    "TodoStorageBackend",
    "StorageSnapshotTodoBackend",
]
