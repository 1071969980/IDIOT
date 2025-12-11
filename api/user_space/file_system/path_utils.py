"""文件系统路径相关工具函数"""
from pathlib import Path
import pathvalidate
from uuid import UUID

def get_user_base_path(user_id: str | UUID) -> Path:
    """获取用户的基础路径

    Args:
        user_id: 用户ID

    Returns:
        用户基础路径 Path 对象
    """
    return Path(f"/{user_id}")

def build_full_path(user_id: str | UUID, relative_path: Path) -> Path:
    """构建完整的文件系统路径

    Args:
        user_id: 用户ID
        relative_path: 相对于用户根目录的路径

    Returns:
        完整路径 Path 对象
    """
    base_path = get_user_base_path(user_id)
    validate_path(relative_path)
    return base_path / relative_path


def build_s3_key(user_id: str | UUID, full_path: Path) -> str:
    """构建S3对象键

    Args:
        user_id: 用户ID
        file_path: 文件路径（可以是相对路径或完整路径）

    Returns:
        S3对象键字符串
    """
    # 要求以完整路径开头
    basepath = get_user_base_path(user_id)
    if not full_path.is_relative_to(basepath):
        raise ValueError("文件路径必须以'/{user_id}'目录开头")
    
    # 构建S3对象键
    return str(
        Path("/user_space/file_system") / full_path
    )


def validate_path(path: Path) -> None:
    """验证路径是否安全

    Args:
        path: 要验证的路径
        allow_absolute: 是否允许绝对路径, 默认不允许

    Returns:
        路径是否安全

    Raises:
        ValueError: 路径不安全时抛出异常
    """
    # 使用pathvalidate进行基本验证
    pathvalidate.validate_filepath(path) # type: ignore


def get_parent_path(file_path: str | Path) -> Path:
    """获取父目录路径

    Args:
        file_path: 文件路径

    Returns:
        父目录路径
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)
    return file_path.parent


def get_filename(file_path: str | Path) -> str:
    """获取文件名

    Args:
        file_path: 文件路径

    Returns:
        文件名
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)
    return file_path.name


def join_paths(*paths: str | Path) -> Path:
    """连接多个路径组件

    Args:
        *paths: 路径组件

    Returns:
        连接后的路径
    """
    result = Path() if not paths else Path(paths[0])
    for path in paths[1:]:
        result = result / path
    return result