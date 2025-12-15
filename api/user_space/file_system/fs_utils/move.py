"""
文件移动工具函数

该模块提供了移动文件和文件夹的实用函数，支持递归移动文件夹。
"""
from pathlib import Path
from typing import Union
from uuid import UUID
from loguru import logger

from api.redis.distributed_lock import RedisDistributedLock
from api.s3_FS import (
    USER_SPACE_BUCKET,
    rename_object,
)
from api.user_space.file_system.path_utils import build_full_path, build_s3_key, validate_path
from api.user_space.file_system.sql_stat.utils import (
    FileSystemItemType,
    _FileSystemItem,
    query_file_system_items_by_path,
    query_file_system_items_by_parent_path,
    update_file_system_item_path,
)

from .exception import (
    HybridFileNotFoundError,
    DatabaseOperationError,
    S3OperationError,
)


async def move_file_or_folder(user_id: UUID, source_path: Path, target_path: Path) -> bool:
    """
    移动文件或文件夹，如果是文件夹则递归移动所有内容

    Args:
        user_id: 用户ID
        source_path: 相对于用户目录( f"/{user_id}" )的源文件或文件夹路径
        target_path: 相对于用户目录( f"/{user_id}" )的目标文件或文件夹路径

    Returns:
        bool: 移动是否成功

    Raises:
        HybridFileNotFoundError: 源路径不存在
        DatabaseOperationError: 数据库操作失败
        S3OperationError: S3操作失败

    Example:
        # 移动文件
        success = await move_file_or_folder(user_id, "documents/test.txt", "archive/test.txt")

        # 移动文件夹及其所有内容
        success = await move_file_or_folder(user_id, "documents/old_folder/", "backup/old_folder/")
    """
    try:
        # 验证路径
        validate_path(source_path)
        validate_path(target_path)

        # 构建完整路径（返回Path对象）
        source_full_path = build_full_path(user_id, source_path)

        # 查询源文件记录（需要转换为str）
        source_records = await query_file_system_items_by_path(user_id, str(source_full_path))

        if not source_records:
            raise HybridFileNotFoundError(f"Source path not found: {source_path}")

        source_record = source_records[0]

        if source_record.item_type == FileSystemItemType.FILE:
            # 移动单个文件（内部会使用分布式锁）
            return await _move_single_file(user_id, source_path, target_path, source_record)
        elif source_record.item_type == FileSystemItemType.FOLDER:
            # 递归移动文件夹（内部会为每个项目使用分布式锁）
            return await _move_folder_recursive(user_id, source_path, target_path, source_record)
        else:
            logger.error(f"Unknown item type: {source_record.item_type} for path: {source_path}")
            return False

    except Exception as e:
        logger.error(f"Failed to move file or folder {source_path} to {target_path}: {e}")
        raise


async def _move_single_file(user_id: UUID, source_path: Path, target_path: Path, source_record: _FileSystemItem) -> bool:
    """
    移动单个文件

    Args:
        user_id: 用户ID
        source_path: 源文件路径
        target_path: 目标文件路径
        source_record: 源文件系统记录

    Returns:
        bool: 移动是否成功
    """
    try:
        # 构建完整路径（返回Path对象）
        source_full_path = build_full_path(user_id, source_path)
        target_full_path = build_full_path(user_id, target_path)

        # 构建S3键（需要传入Path对象）
        source_s3_key = build_s3_key(user_id, source_full_path)
        target_s3_key = build_s3_key(user_id, target_full_path)

        # 使用分布式锁保护单个文件的移动操作
        lock_key = f"HybridFileObject:{source_s3_key}"
        async with RedisDistributedLock(lock_key):
            # 1. 先重命名S3对象
            if not rename_object(USER_SPACE_BUCKET, source_s3_key, target_s3_key):
                logger.warning(f"Failed to rename S3 object from {source_s3_key} to {target_s3_key}")
                raise S3OperationError(f"Failed to rename S3 object: {source_s3_key}")

            # 2. 更新数据库记录中的路径
            success = await update_file_system_item_path(source_record.id, str(target_full_path))
            if not success:
                raise DatabaseOperationError(f"Failed to update database record for: {source_path}")

            logger.info(f"Successfully moved file from {source_path} to {target_path}")
            return True

    except Exception as e:
        logger.error(f"Failed to move file from {source_path} to {target_path}: {e}")
        raise


async def _move_folder_recursive(user_id: UUID, source_folder_path: Path, target_folder_path: Path, folder_record: _FileSystemItem) -> bool:
    """
    递归移动文件夹及其所有内容

    Args:
        user_id: 用户ID
        source_folder_path: 源文件夹路径
        target_folder_path: 目标文件夹路径
        folder_record: 源文件夹记录

    Returns:
        bool: 移动是否成功
    """
    try:
        # 构建完整路径（返回Path对象）
        source_full_path = build_full_path(user_id, source_folder_path)
        target_full_path = build_full_path(user_id, target_folder_path)

        # 1. 递归查找所有子项目
        all_items = await _find_all_items_in_folder(user_id, source_full_path)

        # 2. 按深度排序，确保先处理深层项目再处理浅层项目（避免路径冲突）
        all_items.sort(key=lambda x: x.file_path.count('/'), reverse=True)

        # 3. 移动所有子项目，每个项目单独使用分布式锁
        moved_count = 0
        for item in all_items:
            try:
                # 计算相对路径并构建新的目标路径
                relative_path = str(item.file_path)[len(str(source_full_path)):]
                if relative_path.startswith('/'):
                    relative_path = relative_path[1:]

                item_target_path = target_full_path / relative_path

                # 为每个项目单独使用分布式锁
                item_source_s3_key = build_s3_key(user_id, Path(item.file_path))
                item_target_s3_key = build_s3_key(user_id, item_target_path)
                lock_key = f"HybridFileObject:{item_source_s3_key}"

                async with RedisDistributedLock(lock_key):
                    # 移动S3对象（如果是文件）
                    if item.item_type == FileSystemItemType.FILE:
                        if not rename_object(USER_SPACE_BUCKET, item_source_s3_key, item_target_s3_key):
                            logger.warning(f"Failed to rename S3 object from {item_source_s3_key} to {item_target_s3_key}")
                            continue

                    # 更新数据库记录中的路径
                    success = await update_file_system_item_path(item.id, str(item_target_path))
                    if not success:
                        logger.error(f"Failed to update database record for: {item.file_path}")
                        continue

                    moved_count += 1

            except Exception as e:
                logger.error(f"Failed to move item {item.file_path}: {e}")
                # 继续移动其他项目
                continue

        # 4. 移动文件夹本身（也使用分布式锁）
        folder_source_s3_key = build_s3_key(user_id, source_full_path)
        folder_target_s3_key = build_s3_key(user_id, target_full_path)
        folder_lock_key = f"HybridFileObject:{folder_source_s3_key}"

        async with RedisDistributedLock(folder_lock_key):
            # 移动S3对象
            rename_object(USER_SPACE_BUCKET, folder_source_s3_key, folder_target_s3_key)

            # 更新数据库记录中的路径
            await update_file_system_item_path(folder_record.id, str(target_full_path))
            moved_count += 1

        logger.info(f"Successfully moved folder from {source_folder_path} to {target_folder_path} and {moved_count-1} items")
        return True

    except Exception as e:
        logger.error(f"Failed to move folder from {source_folder_path} to {target_folder_path}: {e}")
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