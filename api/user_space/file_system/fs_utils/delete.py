"""
文件删除工具函数

该模块提供了删除文件和文件夹的实用函数，支持递归删除。
"""
from pathlib import Path
from typing import Union
from uuid import UUID
from loguru import logger

from api.redis.distributed_lock import RedisDistributedLock
from api.s3_FS import (
    USER_SPACE_BUCKET,
    delete_object,
)
from api.user_space.file_system.path_utils import build_full_path, build_s3_key, validate_path
from api.user_space.file_system.sql_stat.utils import (
    FileSystemItemType,
    _FileSystemItem,
    delete_file_system_item_by_id,
    query_file_system_items_by_path,
    query_file_system_items_by_parent_path,
)

from .exception import (
    HybridFileNotFoundError,
    DatabaseOperationError,
    S3OperationError,
)


async def delete_file_or_folder(user_id: UUID, file_path: Path) -> bool:
    """
    删除文件或文件夹，如果是文件夹则递归删除所有内容

    Args:
        user_id: 用户ID
        file_path: 相对于用户home目录的文件或文件夹路径

    Returns:
        bool: 删除是否成功

    Raises:
        HybridFileNotFoundError: 路径不存在
        DatabaseOperationError: 数据库操作失败
        S3OperationError: S3操作失败

    Example:
        # 删除文件
        success = await delete_file_or_folder(user_id, "documents/test.txt")

        # 删除文件夹及其所有内容
        success = await delete_file_or_folder(user_id, "documents/old_folder/")
    """
    try:
        # 验证路径
        validate_path(file_path)

        # 构建完整路径（返回Path对象）
        full_path = build_full_path(user_id, file_path)

        # 查询数据库记录（需要转换为str）
        file_records = await query_file_system_items_by_path(user_id, str(full_path))

        if not file_records:
            raise HybridFileNotFoundError(f"Path not found: {file_path}")

        record = file_records[0]

        if record.item_type == FileSystemItemType.FILE:
            # 删除单个文件（内部会使用分布式锁）
            return await _delete_single_file(user_id, file_path, record)
        elif record.item_type == FileSystemItemType.FOLDER:
            # 递归删除文件夹（内部会为每个项目使用分布式锁）
            return await _delete_folder_recursive(user_id, file_path, record)
        else:
            logger.error(f"Unknown item type: {record.item_type} for path: {file_path}")
            return False

    except Exception as e:
        logger.error(f"Failed to delete file or folder {file_path}: {e}")
        raise


async def _delete_single_file(user_id: UUID, file_path: Path, record: _FileSystemItem) -> bool:
    """
    删除单个文件

    Args:
        user_id: 用户ID
        file_path: 文件路径
        record: 文件系统记录

    Returns:
        bool: 删除是否成功
    """
    try:
        # 构建完整路径（返回Path对象）
        full_path = build_full_path(user_id, file_path)
        # 构建S3键（需要传入Path对象）
        s3_key = build_s3_key(user_id, full_path)

        # 使用分布式锁保护单个文件的删除操作
        lock_key = f"HybridFileObject:{s3_key}"
        async with RedisDistributedLock(lock_key):
            # 1. 先删除S3对象
            if not delete_object(USER_SPACE_BUCKET, s3_key):
                logger.warning(f"Failed to delete S3 object: {s3_key}")

            # 2. 删除数据库记录
            success = await delete_file_system_item_by_id(record.id)
            if not success:
                raise DatabaseOperationError(f"Failed to delete database record for: {file_path}")

            logger.info(f"Successfully deleted file: {file_path}")
            return True

    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {e}")
        raise


async def _delete_folder_recursive(user_id: UUID, folder_path: Path, folder_record: _FileSystemItem) -> bool:
    """
    递归删除文件夹及其所有内容

    Args:
        user_id: 用户ID
        folder_path: 文件夹路径
        folder_record: 文件夹记录

    Returns:
        bool: 删除是否成功
    """
    try:
        # 构建完整路径（返回Path对象）
        full_path = build_full_path(user_id, folder_path)

        # 1. 递归查找所有子项目
        all_items = await _find_all_items_in_folder(user_id, full_path)

        # 2. 按深度排序，确保先删除深层项目再删除浅层项目
        all_items.sort(key=lambda x: x.file_path.count('/'), reverse=True)

        # 3. 删除所有子项目，每个项目单独使用分布式锁
        deleted_count = 0
        for item in all_items:
            try:
                # 为每个项目单独使用分布式锁
                item_path = Path(item.file_path)
                item_s3_key = build_s3_key(user_id, item_path)
                lock_key = f"HybridFileObject:{item_s3_key}"

                async with RedisDistributedLock(lock_key):
                    # 删除S3对象
                    if item.item_type == FileSystemItemType.FILE:
                        delete_object(USER_SPACE_BUCKET, item_s3_key)

                    # 删除数据库记录
                    await delete_file_system_item_by_id(item.id)
                    deleted_count += 1

            except Exception as e:
                logger.error(f"Failed to delete item {item.file_path}: {e}")
                # 继续删除其他项目
                continue

        # 4. 删除文件夹本身（也使用分布式锁）
        folder_s3_key = build_s3_key(user_id, full_path)
        folder_lock_key = f"HybridFileObject:{folder_s3_key}"

        async with RedisDistributedLock(folder_lock_key):
            delete_object(USER_SPACE_BUCKET, folder_s3_key)
            await delete_file_system_item_by_id(folder_record.id)
            deleted_count += 1

        logger.info(f"Successfully deleted folder {folder_path} and {deleted_count-1} items")
        return True

    except Exception as e:
        logger.error(f"Failed to delete folder {folder_path}: {e}")
        raise


async def _find_all_items_in_folder(user_id: UUID, folder_path: Path) -> list[_FileSystemItem]:
    """
    查找文件夹中的所有项目（递归）

    Args:
        user_id: 用户ID
        folder_path: 文件夹完整路径

    Returns:
        list[_FileSystemItem]: 文件夹中的所有项目
    """
    try:
        # query_file_system_items_by_parent_path 已经是递归的，直接返回结果
        all_items = await query_file_system_items_by_parent_path(user_id, str(folder_path))
        return all_items

    except Exception as e:
        logger.error(f"Failed to find items in folder {folder_path}: {e}")
        raise