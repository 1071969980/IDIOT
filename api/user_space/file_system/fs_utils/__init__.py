"""
混合文件系统工具模块

该模块提供了一个统一的文件接口，同时管理关系数据库元数据和 S3 对象存储。
主要功能：
- HybridFileObject: 类似标准文件对象的混合文件对象，支持原生异步上下文管理器
- open_file: 打开文件的便捷函数
- delete_file_or_folder: 删除文件或文件夹的工具函数
- move_file_or_folder: 移动文件或文件夹的工具函数
- list_directory_contents: 列出目录内容的工具函数（类似 ls）
- glob_search: 通配符搜索工具函数（类似 glob）
- 异常处理: 完整的异常处理体系

使用方式：
    # 推荐用法：原生异步上下文管理器
    file_obj = HybridFileObject(user_id, "test.txt", "w", create_if_missing=True)
    async with file_obj as f:
        f.write(b"Hello, World!")

    # 或者使用 open_file 函数
    async with await open_file(user_id, "test.txt", "r") as f:
        content = f.read()

    # 删除文件或文件夹
    success = await delete_file_or_folder(user_id, "documents/test.txt")

    # 移动文件或文件夹
    success = await move_file_or_folder(user_id, "documents/old.txt", "backup/new.txt")
    success = await move_folder(user_id, "documents/old_folder/", "backup/old_folder/")

    # 列出目录内容
    contents = await list_directory_contents(user_id, Path("documents"))

    # 通配符搜索
    files = await glob_search(user_id, "*.txt", working_directory=Path("documents"))

设计原则：
- 先 S3 存储，再数据库记录（确保数据持久化）
- 流式处理支持大文件操作
- 完整的错误处理和资源清理
- 异步优先的 API 设计
"""

# 导出主要类和函数
from .file_object import HybridFileObject
from .open import open_file
from .delete import delete_file_or_folder
from .move import move_file_or_folder
from .list import list_directory_contents, glob_search
from .exception import (
    HybridFileSystemError,
    HybridFileNotFoundError,
    FileAlreadyExistsError,
    DatabaseOperationError,
    S3OperationError,
    TransactionRollbackError,
    InvalidFileModeError,
    LockAcquisitionError,
)

__all__ = [
    # 主要类
    "HybridFileObject",

    # 主要函数
    "open_file",
    "delete_file_or_folder",
    "move_file_or_folder",
    "list_directory_contents",
    "glob_search",

    # 异常类
    "HybridFileSystemError",
    "HybridFileNotFoundError",
    "FileAlreadyExistsError",
    "DatabaseOperationError",
    "S3OperationError",
    "TransactionRollbackError",
    "InvalidFileModeError",
    "LockAcquisitionError",
]