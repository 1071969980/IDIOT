"""
文件操作存储后端

提供统一的存储后端接口，支持内存、本地文件系统和用户空间文件系统。

UserSpaceFileBackend 使用懒加载策略，因为它依赖外部服务（S3 + PostgreSQL + Redis）。
"""

import importlib

from .base import FileOperationsStorageBackend
from .memory import MemoryFileBackend
from .local import LocalFileBackend

__all__ = [
    "FileOperationsStorageBackend",
    "MemoryFileBackend",
    "LocalFileBackend",
    "UserSpaceFileBackend"
]


def __getattr__(name: str):
    """
    PEP 562 懒加载实现

    UserSpaceFileBackend 依赖外部服务（用户空间文件系统），
    使用懒加载策略避免在导入时立即加载这些依赖。

    Args:
        name: 属性名称

    Returns:
        请求的模块或类

    Raises:
        AttributeError: 如果属性不存在
    """
    if name == "UserSpaceFileBackend":
        return importlib.import_module(".user_space", __name__).UserSpaceFileBackend

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
