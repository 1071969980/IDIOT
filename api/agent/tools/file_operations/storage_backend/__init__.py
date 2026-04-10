"""
文件操作存储后端

提供统一的存储后端接口，支持 JuiceFS SDK。
"""

from .base import FileOperationsStorageBackend
from .juicefs_sdk import JuiceFSSdkBackend

__all__ = [
    "FileOperationsStorageBackend",
    "JuiceFSSdkBackend"
]
