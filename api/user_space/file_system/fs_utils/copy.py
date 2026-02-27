"""
文件复制工具函数

该模块提供了复制文件和文件夹的实用函数，支持递归复制文件夹。
"""
from pathlib import Path
from uuid import UUID
from loguru import logger

from api.redis.distributed_lock import RedisDistributedLock
from api.s3_FS import (
    USER_SPACE_BUCKET,
    copy_object,
)
from api.user_space.file_system.path_utils import build_full_path, build_s3_key, validate_path
from api.user_space.file_system.sql_stat.utils import (
    FileSystemItemType,
    _FileSystemItem,
    _FileSystemItemCreate,
    query_file_system_items_by_path,
    query_file_system_items_by_parent_path,
    insert_file_system_item,
)

from .exception import (
    HybridFileNotFoundError,
    DatabaseOperationError,
    S3OperationError,
)


async def copy_file_or_folder(user_id: UUID, source_path: Path, target_path: Path) -> bool:
    """
    复制文件或文件夹，如果是文件夹则递归复制所有内容

    Args:
        user_id: 用户ID
        source_path: 相对于用户目录( f"/{user_id}" )的源文件或文件夹路径
        target_path: 相对于用户目录( f"/{user_id}" )的目标文件或文件夹路径

    Returns:
        bool: 复制是否成功

    Raises:
        HybridFileNotFoundError: 源路径不存在
        DatabaseOperationError: 数据库操作失败
        S3OperationError: S3操作失败

    Example:
        # 复制文件
        success = await copy_file_or_folder(user_id, "documents/test.txt", "archive/test.txt")

        # 复制文件夹及其所有内容
        success = await copy_file_or_folder(user_id, "documents/old_folder/", "backup/old_folder/")
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
            # 复制单个文件（内部会使用分布式锁）
            return await _copy_single_file(user_id, source_path, target_path, source_record)
        elif source_record.item_type == FileSystemItemType.FOLDER:
            # 递归复制文件夹（内部会为每个项目使用分布式锁）
            return await _copy_folder_recursive(user_id, source_path, target_path, source_record)
        else:
            logger.error(f"Unknown item type: {source_record.item_type} for path: {source_path}")
            return False

    except Exception as e:
        logger.error(f"Failed to copy file or folder {source_path} to {target_path}: {e}")
        raise


async def _copy_single_file(user_id: UUID, source_path: Path, target_path: Path, source_record: _FileSystemItem) -> bool:
    """
    复制单个文件

    Args:
        user_id: 用户ID
        source_path: 源文件路径
        target_path: 目标文件路径
        source_record: 源文件系统记录

    Returns:
        bool: 复制是否成功
    """
    try:
        # 构建完整路径（返回Path对象）
        source_full_path = build_full_path(user_id, source_path)
        target_full_path = build_full_path(user_id, target_path)

        # 构建S3键（需要传入Path对象）
        source_s3_key = build_s3_key(user_id, source_full_path)
        target_s3_key = build_s3_key(user_id, target_full_path)

        # 使用分布式锁保护目标文件的复制操作
        lock_key = f"HybridFileObject:{target_s3_key}"
        async with RedisDistributedLock(lock_key):
            # 1. 复制S3对象
            if not copy_object(USER_SPACE_BUCKET, source_s3_key, USER_SPACE_BUCKET, target_s3_key):
                logger.warning(f"Failed to copy S3 object from {source_s3_key} to {target_s3_key}")
                raise S3OperationError(f"Failed to copy S3 object: {source_s3_key}")

            # 2. 创建新的数据库记录（保留源记录）
            new_item = _FileSystemItemCreate(
                user_id=user_id,
                file_path=str(target_full_path),
                item_type=FileSystemItemType.FILE,
                is_encrypted=source_record.is_encrypted,
                metadata=source_record.metadata
            )
            new_id = await insert_file_system_item(new_item)
            if not new_id:
                raise DatabaseOperationError(f"Failed to create database record for: {target_path}")

            logger.info(f"Successfully copied file from {source_path} to {target_path}")
            return True

    except Exception as e:
        logger.error(f"Failed to copy file from {source_path} to {target_path}: {e}")
        raise


async def _copy_folder_recursive(user_id: UUID, source_folder_path: Path, target_folder_path: Path, folder_record: _FileSystemItem) -> bool:
    """
    递归复制文件夹及其所有内容

    Args:
        user_id: 用户ID
        source_folder_path: 源文件夹路径
        target_folder_path: 目标文件夹路径
        folder_record: 源文件夹记录

    Returns:
        bool: 复制是否成功
    """
    try:
        # 构建完整路径（返回Path对象）
        source_full_path = build_full_path(user_id, source_folder_path)
        target_full_path = build_full_path(user_id, target_folder_path)

        # 1. 递归查找所有子项目
        all_items = await _find_all_items_in_folder(user_id, source_full_path)

        # 2. 按深度排序，确保先处理浅层项目再处理深层项目（创建父目录）
        all_items.sort(key=lambda x: x.file_path.count('/'))

        # 3. 复制所有子项目，每个项目单独使用分布式锁
        copied_count = 0
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
                lock_key = f"HybridFileObject:{item_target_s3_key}"

                async with RedisDistributedLock(lock_key):
                    if item.item_type == FileSystemItemType.FILE:
                        # 复制S3对象
                        if not copy_object(USER_SPACE_BUCKET, item_source_s3_key, USER_SPACE_BUCKET, item_target_s3_key):
                            logger.warning(f"Failed to copy S3 object from {item_source_s3_key} to {item_target_s3_key}")
                            continue

                    # 创建新的数据库记录
                    new_item = _FileSystemItemCreate(
                        user_id=user_id,
                        file_path=str(item_target_path),
                        item_type=item.item_type,
                        is_encrypted=item.is_encrypted,
                        metadata=item.metadata
                    )
                    new_id = await insert_file_system_item(new_item)
                    if not new_id:
                        logger.error(f"Failed to create database record for: {item_target_path}")
                        continue

                    copied_count += 1

            except Exception as e:
                logger.error(f"Failed to copy item {item.file_path}: {e}")
                # 继续复制其他项目
                continue

        # 4. 创建目标文件夹本身的记录
        folder_target_s3_key = build_s3_key(user_id, target_full_path)
        folder_lock_key = f"HybridFileObject:{folder_target_s3_key}"

        async with RedisDistributedLock(folder_lock_key):
            new_folder = _FileSystemItemCreate(
                user_id=user_id,
                file_path=str(target_full_path),
                item_type=FileSystemItemType.FOLDER,
                is_encrypted=folder_record.is_encrypted,
                metadata=folder_record.metadata
            )
            new_id = await insert_file_system_item(new_folder)
            if new_id:
                copied_count += 1

        logger.info(f"Successfully copied folder from {source_folder_path} to {target_folder_path} and {copied_count-1} items")
        return True

    except Exception as e:
        logger.error(f"Failed to copy folder from {source_folder_path} to {target_folder_path}: {e}")
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