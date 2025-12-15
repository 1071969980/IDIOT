from dataclasses import dataclass
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import ARRAY, UUID as SQLTYPE_UUID
from pathlib import Path
import re

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

def escape_like_pattern(pattern: str) -> str:
    """
    转义LIKE模式中的特殊字符（%和_），使用反斜杠进行转义
    """
    return re.sub(r'([%_\\])', r'\\\1', pattern)

# 解析SQL文件
sql_file_path = Path(__file__).parent / "FileSystem.sql"
sql_statements = parse_sql_file(sql_file_path)

# 单条SQL语句
INSERT_FILE_SYSTEM_ITEM = sql_statements["InsertFileSystemItem"]
QUERY_FILE_SYSTEM_ITEM_BY_ID = sql_statements["QueryFileSystemItemById"]
QUERY_FILE_SYSTEM_ITEMS_BY_USER = sql_statements["QueryFileSystemItemsByUser"]
QUERY_FILE_SYSTEM_ITEMS_BY_PATH = sql_statements["QueryFileSystemItemsByPath"]
QUERY_FILE_SYSTEM_ITEMS_BY_TYPE = sql_statements["QueryFileSystemItemsByType"]
QUERY_FILE_SYSTEM_ITEMS_BY_PARENT_PATH = sql_statements["QueryFileSystemItemsByParentPath"]
QUERY_FILE_SYSTEM_ITEMS_BY_PARENT_PATH_WITH_DEPTH = sql_statements["QueryFileSystemItemsByParentPathWithDepth"]
UPDATE_FILE_SYSTEM_ITEM = sql_statements["UpdateFileSystemItem"]
UPDATE_FILE_SYSTEM_ITEM_PATH = sql_statements["UpdateFileSystemItemPath"]
UPDATE_FILE_SYSTEM_ITEM_ENCRYPTION = sql_statements["UpdateFileSystemItemEncryption"]
DELETE_FILE_SYSTEM_ITEM_BY_ID = sql_statements["DeleteFileSystemItemById"]
DELETE_FILE_SYSTEM_ITEMS_BY_USER = sql_statements["DeleteFileSystemItemsByUser"]
DELETE_FILE_SYSTEM_ITEMS_BY_PATH = sql_statements["DeleteFileSystemItemsByPath"]
DELETE_FILE_SYSTEM_ITEMS_BY_PARENT_PATH = sql_statements["DeleteFileSystemItemsByParentPath"]
INSERT_FILE_SYSTEM_ITEMS_BATCH = sql_statements["InsertFileSystemItemsBatch"]
UPDATE_FILE_SYSTEM_ITEMS_STATUS = sql_statements["UpdateFileSystemItemsStatus"]
QUERY_FILE_SYSTEM_ITEMS_BY_IDS = sql_statements["QueryFileSystemItemsByIds"]

# list[str]类型的SQL语句（用于创建表和索引）
CREATE_FILE_SYSTEM_TABLE = sql_statements["CreateFileSystemTable"]
CREATE_FILE_SYSTEM_TRIGGERS = sql_statements["CreateFileSystemTriggers"]

# 文件类型枚举
class FileSystemItemType:
    FILE = "file"
    FOLDER = "folder"

    @classmethod
    def all_values(cls) -> List[str]:
        return [cls.FILE, cls.FOLDER]

@dataclass
class _FileSystemItemCreate:
    """创建文件系统项的数据模型"""
    user_id: UUID
    file_path: str
    item_type: str  # 'file' 或 'folder'
    is_encrypted: bool = False
    metadata: dict | None = None

    def __post_init__(self):
        if self.item_type not in FileSystemItemType.all_values():
            raise ValueError(f"item_type must be one of {FileSystemItemType.all_values()}")

@dataclass
class _FileSystemItemUpdate:
    """更新文件系统项的数据模型"""
    id: UUID
    file_path: Optional[str] = None
    item_type: Optional[str] = None
    is_encrypted: Optional[bool] = None
    metadata: Optional[dict] = None

    def __post_init__(self):
        if self.item_type is not None and self.item_type not in FileSystemItemType.all_values():
            raise ValueError(f"item_type must be one of {FileSystemItemType.all_values()}")

@dataclass
class _FileSystemItemBatchCreate:
    """批量创建文件系统项的数据模型"""
    user_ids: List[UUID]
    file_paths: List[str]
    item_types: List[str]
    is_encrypted: List[bool]
    metadata: List[dict | None]

    def __post_init__(self):
        list_lengths = [len(self.user_ids), len(self.file_paths),
                       len(self.item_types), len(self.is_encrypted), len(self.metadata)]
        if len(set(list_lengths)) != 1:
            raise ValueError("All input lists must have the same length")

        for item_type in self.item_types:
            if item_type not in FileSystemItemType.all_values():
                raise ValueError(f"item_type must be one of {FileSystemItemType.all_values()}")

@dataclass
class _FileSystemItem:
    """文件系统项的数据模型"""
    id: UUID
    user_id: UUID
    file_path: str
    item_type: str  # 'file' 或 'folder'
    is_encrypted: bool
    metadata: dict | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self):
        if self.item_type not in FileSystemItemType.all_values():
            raise ValueError(f"item_type must be one of {FileSystemItemType.all_values()}")

def _row_to_file_system_item(row) -> _FileSystemItem:
    """将数据库行转换为 FileSystemItem 对象"""
    return _FileSystemItem(
        id=row.id,
        user_id=row.user_id,
        file_path=row.file_path,
        item_type=row.item_type,
        is_encrypted=row.is_encrypted,
        metadata=row.metadata,
        created_at=row.created_at,
        updated_at=row.updated_at
    )

async def create_table() -> None:
    """创建文件系统表和相关索引、触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # 创建表和索引
        for stmt in CREATE_FILE_SYSTEM_TABLE:
            await conn.execute(text(stmt))

        # 创建触发器
        for stmt in CREATE_FILE_SYSTEM_TRIGGERS:
            await conn.execute(text(stmt))

        await conn.commit()

async def insert_file_system_item(item_data: _FileSystemItemCreate) -> UUID:
    """插入单个文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_FILE_SYSTEM_ITEM).bindparams(
                bindparam("user_id", type_=SQLTYPE_UUID),
            ),
            {
                "user_id": item_data.user_id,
                "file_path": item_data.file_path,
                "item_type": item_data.item_type,
                "is_encrypted": item_data.is_encrypted,
                "metadata": item_data.metadata,
            }
        )
        await conn.commit()
        return result.scalar()

async def query_file_system_item_by_id(item_id: UUID) -> Optional[_FileSystemItem]:
    """根据ID查询单个文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_FILE_SYSTEM_ITEM_BY_ID).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {"id_value": item_id}
        )
        row = result.first()
        return _row_to_file_system_item(row) if row else None

async def query_file_system_items_by_user(user_id: UUID) -> List[_FileSystemItem]:
    """查询用户的所有文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_FILE_SYSTEM_ITEMS_BY_USER).bindparams(
                bindparam("user_id_value", type_=SQLTYPE_UUID),
            ),
            {"user_id_value": user_id}
        )
        return [_row_to_file_system_item(row) for row in result.fetchall()]

async def query_file_system_items_by_path(user_id: UUID, file_path: str) -> List[_FileSystemItem]:
    """根据路径查询文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_FILE_SYSTEM_ITEMS_BY_PATH).bindparams(
                bindparam("user_id_value", type_=SQLTYPE_UUID),
            ),
            {
                "user_id_value": user_id,
                "file_path_value": file_path,
            }
        )
        return [_row_to_file_system_item(row) for row in result.fetchall()]

async def query_file_system_items_by_type(user_id: UUID, item_type: str) -> List[_FileSystemItem]:
    """根据类型查询文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_FILE_SYSTEM_ITEMS_BY_TYPE).bindparams(
                bindparam("user_id_value", type_=SQLTYPE_UUID),
            ),
            {
                "user_id_value": user_id,
                "item_type_value": item_type,
            }
        )
        return [_row_to_file_system_item(row) for row in result.fetchall()]

async def query_file_system_items_by_parent_path(user_id: UUID, parent_path: str) -> List[_FileSystemItem]:
    """递归查找指定路径下的所有子项目（不包含父路径本身）"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # 构建路径模式，例如: '/home/user/%' 匹配所有子路径
        if not parent_path.endswith('/'):
            parent_path += '/'
        # 对路径进行转义处理，然后添加通配符
        escaped_path = escape_like_pattern(parent_path)
        pattern = escaped_path + '%'

        result = await conn.execute(
            text(QUERY_FILE_SYSTEM_ITEMS_BY_PARENT_PATH).bindparams(
                bindparam("user_id_value", type_=SQLTYPE_UUID),
            ),
            {
                "user_id_value": user_id,
                "parent_path_pattern": pattern,
            }
        )
        return [_row_to_file_system_item(row) for row in result.fetchall()]

async def query_file_system_items_by_parent_path_with_depth(
    user_id: UUID,
    parent_path: str,
    max_depth: int | None = 1
) -> List[_FileSystemItem]:
    """查找指定路径下的子项目，支持深度限制（max_depth=1表示仅一级子目录，None表示无限制）"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # 确保父路径以/结尾
        if not parent_path.endswith('/'):
            parent_path += '/'

        # 用于LIKE匹配的模式（对路径进行转义处理）
        escaped_path = escape_like_pattern(parent_path)
        pattern = escaped_path + '%'

        # 用于计算的干净父路径（去掉末尾的/）
        parent_path_clean = parent_path.rstrip('/')

        result = await conn.execute(
            text(QUERY_FILE_SYSTEM_ITEMS_BY_PARENT_PATH_WITH_DEPTH).bindparams(
                bindparam("user_id_value", type_=SQLTYPE_UUID),
            ),
            {
                "user_id_value": user_id,
                "parent_path_pattern": pattern,
                "parent_path_clean": parent_path_clean,
                "max_depth": max_depth,
            }
        )
        return [_row_to_file_system_item(row) for row in result.fetchall()]

async def update_file_system_item(item_data: _FileSystemItemUpdate) -> bool:
    """更新文件系统项"""
    if item_data.file_path is None or item_data.item_type is None or item_data.is_encrypted is None:
        raise ValueError("file_path, item_type, and is_encrypted must be provided for full update")

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_FILE_SYSTEM_ITEM).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {
                "id_value": item_data.id,
                "file_path_value": item_data.file_path,
                "item_type_value": item_data.item_type,
                "is_encrypted_value": item_data.is_encrypted,
                "metadata_value": item_data.metadata,
            }
        )
        await conn.commit()
        return result.rowcount > 0

async def update_file_system_item_path(item_id: UUID, new_file_path: str) -> bool:
    """更新文件系统项的路径"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_FILE_SYSTEM_ITEM_PATH).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {
                "id_value": item_id,
                "new_file_path_value": new_file_path,
            }
        )
        await conn.commit()
        return result.rowcount > 0

async def update_file_system_item_encryption(item_id: UUID, is_encrypted: bool) -> bool:
    """更新文件系统项的加密状态"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_FILE_SYSTEM_ITEM_ENCRYPTION).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {
                "id_value": item_id,
                "is_encrypted_value": is_encrypted,
            }
        )
        await conn.commit()
        return result.rowcount > 0

async def delete_file_system_item_by_id(item_id: UUID) -> bool:
    """根据ID删除文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_FILE_SYSTEM_ITEM_BY_ID).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {"id_value": item_id}
        )
        await conn.commit()
        return result.rowcount > 0

async def delete_file_system_items_by_user(user_id: UUID) -> int:
    """删除用户的所有文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_FILE_SYSTEM_ITEMS_BY_USER).bindparams(
                bindparam("user_id_value", type_=SQLTYPE_UUID),
            ),
            {"user_id_value": user_id}
        )
        await conn.commit()
        return result.rowcount

async def delete_file_system_items_by_path(user_id: UUID, file_path: str) -> int:
    """根据路径删除文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_FILE_SYSTEM_ITEMS_BY_PATH).bindparams(
                bindparam("user_id_value", type_=SQLTYPE_UUID),
            ),
            {
                "user_id_value": user_id,
                "file_path_value": file_path,
            }
        )
        await conn.commit()
        return result.rowcount

async def delete_file_system_items_by_parent_path(user_id: UUID, parent_path: str) -> int:
    """递归删除指定路径下的所有子项目（不包含父路径本身），返回删除数量"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # 构建路径模式
        if not parent_path.endswith('/'):
            parent_path += '/'
        # 对路径进行转义处理
        escaped_path = escape_like_pattern(parent_path)
        pattern = escaped_path + '%'

        result = await conn.execute(
            text(DELETE_FILE_SYSTEM_ITEMS_BY_PARENT_PATH).bindparams(
                bindparam("user_id_value", type_=SQLTYPE_UUID),
            ),
            {
                "user_id_value": user_id,
                "parent_path_pattern": pattern,
            }
        )
        await conn.commit()
        return result.rowcount
async def insert_file_system_items_batch(items_data: _FileSystemItemBatchCreate) -> List[UUID]:
    """批量插入文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_FILE_SYSTEM_ITEMS_BATCH).bindparams(
                bindparam("user_ids_list", type_=ARRAY(SQLTYPE_UUID)),
            ),
            {
                "user_ids_list": items_data.user_ids,
                "file_paths_list": items_data.file_paths,
                "item_types_list": items_data.item_types,
                "is_encrypted_list": items_data.is_encrypted,
                "metadata_list": items_data.metadata,
            }
        )
        await conn.commit()
        return [row[0] for row in result.fetchall()]

async def insert_file_system_items_from_list(items: List[_FileSystemItemCreate]) -> List[UUID]:
    """从单个文件系统项列表批量创建文件系统项"""
    if not items:
        return []

    batch_data = _FileSystemItemBatchCreate(
        user_ids=[item.user_id for item in items],
        file_paths=[item.file_path for item in items],
        item_types=[item.item_type for item in items],
        is_encrypted=[item.is_encrypted for item in items],
        metadata=[item.metadata for item in items]
    )

    return await insert_file_system_items_batch(batch_data)

async def update_file_system_items_status(item_ids: List[UUID], is_encrypted: bool) -> int:
    """批量更新文件系统项的加密状态"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_FILE_SYSTEM_ITEMS_STATUS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {
                "is_encrypted_value": is_encrypted,
                "ids_list": item_ids,
            }
        )
        await conn.commit()
        return result.rowcount

async def query_file_system_items_by_ids(item_ids: List[UUID]) -> List[_FileSystemItem]:
    """根据ID列表批量查询文件系统项"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_FILE_SYSTEM_ITEMS_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {
                "ids_list": item_ids,
            }
        )
        return [_row_to_file_system_item(row) for row in result.fetchall()]