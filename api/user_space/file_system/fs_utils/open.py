"""
文件打开工具函数

该模块提供了打开混合文件系统文件的便捷函数。
"""
from pathlib import Path
from typing import Union
from uuid import UUID
from loguru import logger

from api.user_space.file_system.path_utils import validate_path
from .file_object import HybridFileObject


async def open_file(
    user_id: Union[str, UUID],
    file_path: Path,
    mode: str = 'r',
    create_if_missing: bool = False
) -> HybridFileObject:
    """
    打开混合文件系统的文件

    Args:
        user_id: 用户ID
        file_path: 相对于用户home目录的文件路径
        mode: 文件打开模式，支持 'r' 或 'w'
        create_if_missing: 写入模式下文件不存在时是否自动创建

    Returns:
        HybridFileObject: 混合文件对象

    Example:
        # 读取文件
        async with await open_file(user_id, "documents/test.txt", "r") as f:
            content = f.read()

        # 写入文件
        async with await open_file(user_id, "documents/new.txt", "w", create_if_missing=True) as f:
            f.write(b"Hello, World!")
    """
    # 验证路径
    validate_path(file_path)

    # 创建混合文件对象
    file_obj = HybridFileObject(user_id, file_path, mode, create_if_missing)

    logger.info(f"Opened file: {file_path} in mode {mode} for user {user_id}")

    return file_obj