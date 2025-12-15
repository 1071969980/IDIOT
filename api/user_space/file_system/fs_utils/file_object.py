"""
混合文件对象实现

该模块提供了 HybridFileObject 类，模拟标准文件对象行为，
在内部协调 S3 对象存储和关系数据库，提供统一的文件操作接口。
"""
import asyncio
import io
import os
import tempfile
from pathlib import Path
from typing import Optional, Union
from uuid import UUID

from loguru import logger

from api.redis.distributed_lock import RedisDistributedLock
from api.s3_FS import (
    USER_SPACE_BUCKET,
    upload_object,
    download_object,
)
from api.user_space.file_system.path_utils import (
    build_full_path,
    build_s3_key,
    get_parent_path,
    get_user_base_path,
)
from api.user_space.file_system.sql_stat.utils import (
    FileSystemItemType,
    _FileSystemItem,
    _FileSystemItemCreate,
    _FileSystemItemUpdate,
    query_file_system_items_by_path,
    insert_file_system_item,
    update_file_system_item,
)

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
from .create_dir import create_directory_recursive

class HybridFileObject(io.IOBase):
    """
    混合文件对象，模拟标准文件对象行为

    该类在内部协调 S3 对象存储和关系数据库，提供统一的文件操作接口。
    支持读取 ('r') 和写入 ('w') 模式。
    """

    def __init__(self, user_id: Union[str, UUID], file_path: Path, mode: str = 'r',
                 create_if_missing: bool = False, create_directories: bool = True):
        """
        初始化混合文件对象

        Args:
            user_id: 用户ID
            file_path: 相对于用户目录( f"/{user_id}" )的文件路径
            mode: 文件打开模式，支持 'r' 或 'w'
            create_if_missing: 写入模式下文件不存在时是否自动创建
            create_directories: 创建文件时是否自动创建不存在的目录结构
        """
        super().__init__()

        # 验证模式
        if mode not in ('r', 'w'):
            raise InvalidFileModeError(f"Unsupported mode: {mode}. Only 'r' and 'w' are supported")

        self.user_id = UUID(str(user_id))
        self.file_path = file_path
        self.mode = mode
        self.create_if_missing = create_if_missing
        self.create_directories = create_directories

        # 构建完整路径和 S3 键
        self.full_path = build_full_path(self.user_id, file_path)
        self.s3_key = build_s3_key(self.user_id, self.full_path)

        # 内部状态 - 延迟初始化
        self._file_record: _FileSystemItem | None = None
        self._temp_file: tempfile._TemporaryFileWrapper | None = None
        self._closed = False
        self._modified = False
        self._initialized = False

        # 分布式锁相关
        self._lock: RedisDistributedLock | None = None

    async def _init_read_mode_async(self):
        """异步初始化读取模式"""
        # 检查文件是否存在
        file_records = await query_file_system_items_by_path(self.user_id, str(self.full_path))
        if not file_records:
            raise HybridFileNotFoundError(f"File not found: {self.file_path}")

        self._file_record = file_records[0]

        # 检查是否为文件类型
        if self._file_record.item_type != FileSystemItemType.FILE:
            raise HybridFileNotFoundError(f"Path is not a file: {self.file_path}")

        # 创建临时文件用于缓存 S3 内容
        self._temp_file = tempfile.NamedTemporaryFile(mode='w+b', delete=False)

        # 从 S3 下载文件内容到临时文件
        try:
            if not download_object(self._temp_file, USER_SPACE_BUCKET, self.s3_key):
                raise S3OperationError(f"Failed to download file from S3: {self.s3_key}")

            # 重置文件指针到开头
            self._temp_file.seek(0)

        except Exception as e:
            self._temp_file.close()
            os.unlink(self._temp_file.name)
            raise S3OperationError(f"S3 download failed: {e}")

        self._initialized = True

    async def _init_write_mode_async(self):
        """异步初始化写入模式"""
        # 检查文件是否已存在
        file_records = await query_file_system_items_by_path(self.user_id, str(self.full_path))

        if file_records:
            self._file_record = file_records[0]

            # 检查是否为文件类型
            if self._file_record.item_type != FileSystemItemType.FILE:
                raise HybridFileNotFoundError(f"Path is not a file: {self.file_path}")

            # 文件已存在，下载现有内容用于编辑（可选）
            self._temp_file = tempfile.NamedTemporaryFile(mode='w+b', delete=False)
            try:
                download_object(self._temp_file, USER_SPACE_BUCKET, self.s3_key)
                self._temp_file.seek(0)
            except Exception:
                # 如果下载失败，创建空文件
                self._temp_file.seek(0)
                self._temp_file.truncate()
        else:
            # 文件不存在，根据 create_if_missing 参数决定是否创建
            if not self.create_if_missing:
                raise HybridFileNotFoundError(f"File not found: {self.file_path}")

            # 检查并创建目录结构（如果启用）
            if self.create_directories:
                await self._ensure_directory_structure()
            else:
                # 不创建目录，但需要检查目录是否存在
                await self._check_directory_exists()

            # 创建新的临时文件
            self._temp_file = tempfile.NamedTemporaryFile(mode='w+b', delete=False)
            self._file_record = None

        self._initialized = True

    def readable(self) -> bool:
        """检查文件是否可读"""
        return self.mode == 'r' and not self._closed

    def writable(self) -> bool:
        """检查文件是否可写"""
        return self.mode == 'w' and not self._closed

    def read(self, size: int = -1) -> bytes:
        """读取文件内容"""
        if not self.readable():
            raise ValueError("File is not readable")

        if self._temp_file.closed:
            raise ValueError("File is closed")

        return self._temp_file.read(size)

    def write(self, data: bytes) -> int:
        """写入数据到文件"""
        if not self.writable():
            raise ValueError("File is not writable")

        if self._temp_file.closed:
            raise ValueError("File is closed")

        result = self._temp_file.write(data)
        self._modified = True
        return result

    def seek(self, offset: int, whence: int = 0) -> int:
        """移动文件指针"""
        if self._temp_file.closed:
            raise ValueError("File is closed")

        return self._temp_file.seek(offset, whence)

    def tell(self) -> int:
        """获取当前文件指针位置"""
        if self._temp_file.closed:
            raise ValueError("File is closed")

        return self._temp_file.tell()

    def flush(self) -> None:
        """刷新缓冲区"""
        if self._temp_file and not self._temp_file.closed:
            self._temp_file.flush()

    async def close(self) -> None:
        """关闭文件并保存更改"""
        if self._closed:
            return

        try:
            # 如果是写入模式且文件被修改，则保存到 S3 和数据库
            if self.mode == 'w' and self._modified:
                await self._save_changes()
            else:
                # 对于读取模式或未修改的写入模式，只需要关闭临时文件
                if self._temp_file and not self._temp_file.closed:
                    self._temp_file.close()
                    # 删除临时文件
                    try:
                        os.unlink(self._temp_file.name)
                    except OSError:
                        pass  # 忽略删除临时文件的错误
                    self._temp_file = None

            self._closed = True

        except Exception as e:
            logger.error(f"Error closing file: {e}")
            raise

    async def _ensure_directory_structure(self) -> None:
        """确保文件的目录结构存在，如果不存在则创建"""
        try:
            parent_path = get_parent_path(self.full_path)

            # 如果已经是用户根目录，则无需创建
            if parent_path == get_user_base_path(self.user_id):
                return

            # 检查父目录是否存在
            parent_records = await query_file_system_items_by_path(self.user_id, str(parent_path))

            if not parent_records:
                # 父目录不存在，递归创建目录结构
                await create_directory_recursive(self.user_id, parent_path)
            else:
                # 父目录存在，检查是否为文件夹类型
                parent_record = parent_records[0]
                if parent_record.item_type != FileSystemItemType.FOLDER:
                    raise HybridFileNotFoundError(f"Parent path is not a directory: {parent_path}")

        except Exception as e:
            logger.error(f"Failed to ensure directory structure for {self.file_path}: {e}")
            raise DatabaseOperationError(f"Directory structure check failed: {e}")

    async def _check_directory_exists(self) -> None:
        """检查文件的目录结构是否存在，如果不存在则抛出异常"""
        try:
            parent_path = get_parent_path(self.full_path)

            # 如果已经是用户根目录，则无需检查
            if parent_path == get_user_base_path(self.user_id):
                return

            # 检查父目录是否存在
            parent_records = await query_file_system_items_by_path(self.user_id, str(parent_path))

            if not parent_records:
                raise HybridFileNotFoundError(f"Parent directory does not exist: {parent_path}")
            else:
                # 验证父目录类型
                parent_record = parent_records[0]
                if parent_record.item_type != FileSystemItemType.FOLDER:
                    raise HybridFileNotFoundError(f"Parent path is not a directory: {parent_path}")

        except Exception as e:
            logger.error(f"Failed to check directory structure for {self.file_path}: {e}")
            raise DatabaseOperationError(f"Directory structure check failed: {e}")

    async def _save_changes(self):
        """保存更改到 S3 和数据库"""
        if not self._temp_file:
            return

        temp_file_path = None

        try:
            # 确保所有数据都写入磁盘并关闭文件句柄
            self._temp_file.flush()
            temp_file_path = self._temp_file.name
            self._temp_file.close()
            self._temp_file = None

            # 1. 先上传到 S3
            with open(temp_file_path, 'rb') as f:
                if not upload_object(f, USER_SPACE_BUCKET, self.s3_key):
                    raise S3OperationError(f"Failed to upload file to S3: {self.s3_key}")

            logger.info(f"Successfully uploaded file to S3: {self.s3_key}")

            # 2. S3 成功后，更新数据库记录
            if self._file_record is None:
                # 创建新的数据库记录
                file_data = _FileSystemItemCreate(
                    user_id=self.user_id,
                    file_path=str(self.full_path),
                    item_type=FileSystemItemType.FILE,
                    is_encrypted=False  # 根据需求，这个函数不创建加密文件
                )
                await insert_file_system_item(file_data)
                logger.info(f"Created new database record for: {self.file_path}")

            else:
                # 更新现有记录（主要更新修改时间，通过触发器自动处理）
                update_data = _FileSystemItemUpdate(
                    id=self._file_record.id,
                    file_path=self._file_record.file_path,
                    item_type=self._file_record.item_type,
                    is_encrypted=self._file_record.is_encrypted,
                )
                await update_file_system_item(update_data)
                logger.info(f"Updated database record for: {self.file_path}")

        except Exception as e:
            logger.error(f"Save changes failed: {e}")

            # 根据错误类型抛出相应的异常
            if "S3" in str(e) or "upload" in str(e):
                raise S3OperationError(f"S3 upload failed: {e}")
            else:
                raise DatabaseOperationError(f"Database operation failed: {e}")

        finally:
            # 清理临时文件
            if temp_file_path:
                try:
                    os.unlink(temp_file_path)
                except OSError as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")
    async def __aenter__(self):
        """异步上下文管理器入口"""
        # 创建分布式锁
        lock_key = f"HybridFileObject:{self.s3_key}"
        self._lock = RedisDistributedLock(lock_key)

        # 获取锁
        try:
            if not await self._lock.acquire():
                raise LockAcquisitionError(f"Failed to acquire lock for file: {self.file_path}")
            logger.info(f"Acquired distributed lock for file: {self.file_path}")
        except Exception as e:
            raise LockAcquisitionError(f"Lock acquisition failed for file {self.file_path}: {e}")

        # 在锁保护下进行异步初始化
        try:
            if not self._initialized:
                if self.mode == 'r':
                    await self._init_read_mode_async()
                else:  # mode == 'w'
                    await self._init_write_mode_async()
                logger.info(f"File initialized successfully: {self.file_path}")
        except Exception as e:
            # 初始化失败时释放锁
            try:
                await self._lock.release()
                self._lock = None
            except Exception:
                pass
            raise e

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        try:
            # 先关闭文件
            await self.close()
        finally:
            # 释放分布式锁
            if self._lock:
                try:
                    await self._lock.release()
                    logger.info(f"Released distributed lock for file: {self.file_path}")
                except Exception as e:
                    logger.error(f"Failed to release lock for file {self.file_path}: {e}")
                finally:
                    self._lock = None

        return False  # 不抑制异常