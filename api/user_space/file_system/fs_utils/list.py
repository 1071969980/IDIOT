"""
文件系统查询工具函数

该模块提供了类似 ls（列出文件夹内容）和 glob（通配符搜索）的功能。
基于现有的混合文件系统架构，使用 pathlib.Path 进行路径操作。
"""

from pathlib import Path
from uuid import UUID
from loguru import logger

from api.user_space.file_system.path_utils import build_full_path, validate_path
from api.user_space.file_system.sql_stat.utils import (
    _FileSystemItem,
    query_file_system_items_by_parent_path_with_depth,
    query_file_system_items_by_parent_path,
)

from .exception import (
    DatabaseOperationError,
)


def _path_contains_hidden_component(file_path: Path, base_path: Path) -> bool:
    """检查路径中是否包含隐藏组件（包括隐藏文件夹内的文件）

    Args:
        file_path: 完整文件路径
        base_path: 基础路径（用户根目录或工作目录）

    Returns:
        bool: 路径中是否包含隐藏组件
    """
    try:
        relative_path = file_path.relative_to(base_path)
        # 检查相对路径的每个组件是否为隐藏
        return any(component.startswith(".") for component in relative_path.parts)
    except ValueError:
        # 如果无法计算相对路径，保守处理，检查完整路径
        return any(component.startswith(".") for component in file_path.parts)


def _is_immediate_child(full_parent: Path, item_path: Path) -> bool:
    """使用 pathlib 检查是否为直接子项

    Args:
        full_parent: 父目录完整路径
        item_path: 项目路径

    Returns:
        bool: 是否为直接子项
    """
    return item_path.parent == full_parent


def _get_relative_path(item_path: Path, base_path: Path) -> Path:
    """使用 pathlib 获取相对路径

    Args:
        item_path: 项目完整路径
        base_path: 基础路径

    Returns:
        Path: 相对路径
    """
    try:
        return item_path.relative_to(base_path)
    except ValueError:
        # 如果不是相对路径，返回原路径
        return item_path


async def list_directory_contents(
    user_id: UUID,
    directory_path: Path,
    *,
    include_hidden: bool = False,
) -> list[_FileSystemItem]:
    """
    列出目录的直接子项（类似 ls 命令）

    Args:
        user_id: 用户ID
        directory_path: 相对于用户目录的目录路径
        include_hidden: 是否包含隐藏文件，默认不包含

    Returns:
        List[_FileSystemItem]: 目录中的直接子项列表，按文件名排序

    Raises:
        HybridFileSystemError: 路径验证失败
        DatabaseOperationError: 数据库操作失败

    Example:
        # 列出用户根目录内容
        contents = await list_directory_contents(user_id, Path("."))

        # 列出 documents 目录内容
        contents = await list_directory_contents(user_id, Path("documents"))

        # 包含隐藏文件
        contents = await list_directory_contents(user_id, Path("."), include_hidden=True)
    """
    try:
        # 验证路径
        validate_path(directory_path)

        # 构建完整路径
        full_path = build_full_path(user_id, directory_path)
        logger.debug(f"Listing directory contents for: {full_path}")

        # 获取深度为1的所有项目（包含目录本身）
        all_items = await query_file_system_items_by_parent_path_with_depth(
            user_id, str(full_path), max_depth=1
        )

        # 构建用户基础路径用于隐藏文件检测
        user_base_path = Path(f"/{user_id}")

        # 过滤结果
        result = []
        for item in all_items:
            item_path = Path(item.file_path)

            # 跳过目录本身
            if item_path == full_path:
                continue

            # 只保留直接子项
            if not _is_immediate_child(full_path, item_path):
                continue

            # 隐藏文件过滤 - 检查完整路径中的所有组件
            if not include_hidden and _path_contains_hidden_component(item_path, user_base_path):
                continue

            result.append(item)

        logger.debug(f"Found {len(result)} items in directory {directory_path}")
        return result

    except Exception as e:
        logger.error(f"Failed to list directory contents {directory_path}: {e}")
        raise DatabaseOperationError(f"Directory listing failed: {e}") from e


async def glob_search(
    user_id: UUID,
    pattern: str,
    working_directory: Path = Path(),
    *,
    include_hidden: bool = False,
) -> list[_FileSystemItem]:
    """
    使用通配符模式搜索文件（类似 glob 命令）

    Args:
        user_id: 用户ID
        pattern: glob 模式字符串，支持 *, ?, [], ** 等通配符
        working_directory: 工作目录（相对路径基准），默认为当前目录
        include_hidden: 是否包含隐藏文件，默认不包含

    Returns:
        List[_FileSystemItem]: 匹配模式的文件列表，按路径排序

    Raises:
        HybridFileSystemError: 路径验证失败
        DatabaseOperationError: 数据库操作失败

    Example:
        # 搜索当前目录下所有 .txt 文件
        files = await glob_search(user_id, "*.txt")

        # 递归搜索所有子目录的 .py 文件
        files = await glob_search(user_id, "**/*.py")

        # 在 documents 目录下搜索所有文件
        files = await glob_search(user_id, "*", working_directory=Path("documents"))

        # 搜索特定模式的文件
        files = await glob_search(user_id, "test_?.py", include_hidden=True)
    """
    try:
        # 验证路径
        validate_path(working_directory)

        # 构建完整基础路径
        base_path = build_full_path(user_id, working_directory)
        logger.debug(f"Glob search in {base_path} with pattern: {pattern}")

        # 递归获取基础路径下的所有项目
        all_items = await query_file_system_items_by_parent_path(user_id, str(base_path))

        # 构建用户基础路径用于隐藏文件检测
        user_base_path = Path(f"/{user_id}")

        # 使用 pathlib 进行模式匹配
        result = []

        for item in all_items:
            item_path = Path(item.file_path)

            # 跳过基础目录本身
            if item_path == base_path:
                continue

            # 隐藏文件过滤 - 检查完整路径中的所有组件
            if not include_hidden and _path_contains_hidden_component(item_path, user_base_path):
                continue

            # 获取相对路径并进行模式匹配
            try:
                relative_path = _get_relative_path(item_path, base_path)

                # 使用 pathlib 的 match 方法进行 glob 匹配
                if relative_path.match(pattern):
                    result.append(item)

            except ValueError:
                # 如果无法计算相对路径，跳过该项目
                continue

        logger.debug(f"Found {len(result)} items matching pattern '{pattern}'")
        return result

    except Exception as e:
        logger.error(f"Failed to glob search pattern '{pattern}': {e}")
        raise DatabaseOperationError(f"Glob search failed: {e}") from e