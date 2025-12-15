
from pathlib import Path
from uuid import UUID

from loguru import logger

from api.user_space.file_system.path_utils import (
    get_parent_path,
    get_user_base_path,
)
from api.user_space.file_system.sql_stat.utils import (
    FileSystemItemType,
    _FileSystemItemCreate,
    insert_file_system_item,
    query_file_system_items_by_path,
)

from .exception import (
    DatabaseOperationError,
    HybridFileNotFoundError,
    HybridFileSystemError,
)


async def create_directory_recursive(user_id: UUID, full_path: Path) -> None:
    """递归创建目录结构"""
    try:
        if not full_path.is_relative_to(get_user_base_path(user_id)):
            raise HybridFileSystemError(f"Path is outside of user directory: {full_path}")

        # 获取父目录
        parent_path = get_parent_path(full_path)

        # 如果已经是用户根目录，停止递归
        if parent_path == get_user_base_path(user_id):
            pass
        else:
            # 检查父目录是否存在
            parent_records = await query_file_system_items_by_path(user_id, str(parent_path))

            if not parent_records:
                # 父目录不存在，递归创建
                await create_directory_recursive(user_id, parent_path)
            else:
                # 验证父目录类型
                parent_record = parent_records[0]
                if parent_record.item_type != FileSystemItemType.FOLDER:
                    raise HybridFileNotFoundError(f"Parent path is not a directory: {parent_path}")

        # 创建当前目录
        dir_data = _FileSystemItemCreate(
            user_id=user_id,
            file_path=str(full_path),
            item_type=FileSystemItemType.FOLDER,
            is_encrypted=False,
        )
        await insert_file_system_item(dir_data)
        logger.info(f"Created directory: {full_path}")

    except Exception as e:
        logger.error(f"Failed to create directory {full_path}: {e}")
        raise DatabaseOperationError(f"Directory creation failed: {e}")
