"""
混合文件系统异常类定义

该模块定义了混合文件系统中使用的所有异常类，提供清晰的错误类型和错误处理。
"""


class HybridFileSystemError(Exception):
    """混合文件系统基础异常类"""
    pass


class HybridFileNotFoundError(HybridFileSystemError):
    """文件未找到异常"""
    pass


class FileAlreadyExistsError(HybridFileSystemError):
    """文件已存在异常"""
    pass


class DatabaseOperationError(HybridFileSystemError):
    """数据库操作异常"""
    pass


class S3OperationError(HybridFileSystemError):
    """S3 操作异常"""
    pass


class TransactionRollbackError(HybridFileSystemError):
    """事务回滚异常"""
    pass


class InvalidFileModeError(HybridFileSystemError):
    """无效文件模式异常"""
    pass


class LockAcquisitionError(HybridFileSystemError):
    """锁获取失败异常"""
    pass