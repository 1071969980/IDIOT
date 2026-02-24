"""
目录列表相关的实用工具模块
提供通用的目录列表格式化和处理功能
"""

from typing import Dict, List, Optional
from ..storage_backend.base import DirectoryItem


def format_directory_tree(
    items: List[DirectoryItem],
    path: str = ".",
    show_empty_dirs: bool = True
) -> str:
    """
    格式化目录树显示

    Args:
        items: 目录项列表
        path: 当前目录路径
        show_empty_dirs: 是否显示空目录

    Returns:
        格式化的目录树字符串
    """
    if not items:
        return f"目录信息：{path}\n{'空目录' if show_empty_dirs else ''}"

    # Group items by type (directories first, then files)
    directories = [item for item in items if item.type == "directory"]
    files = [item for item in items if item.type == "file"]

    # Build content lines with proper tree formatting
    content_lines = []

    # Add directories first
    for i, item in enumerate(directories):
        is_last = (i == len(directories) - 1) and (len(files) == 0)
        icon = "[DIR]"
        connector = "└── " if is_last else "├── "
        line = f"{connector}{icon} {item.name}"
        content_lines.append(line)

    # Add files after directories
    for i, item in enumerate(files):
        is_last = i == len(files) - 1
        icon = "[FILE]"
        connector = "└── " if is_last else "├── "
        line = f"{connector}{icon} {item.name}"
        content_lines.append(line)

    # Create title and combine
    title = f"目录信息：{path}\n"
    return title + "\n".join(content_lines)


def filter_directory_items(
    items: List[DirectoryItem],
    include_files: bool = True,
    include_directories: bool = True,
    name_filter: Optional[str] = None
) -> List[DirectoryItem]:
    """
    根据条件过滤目录项

    Args:
        items: 目录项列表
        include_files: 是否包含文件
        include_directories: 是否包含目录
        name_filter: 名称过滤器（包含指定字符串的才保留）

    Returns:
        过滤后的目录项列表
    """
    filtered_items = []

    for item in items:
        # Check type filter
        if item.type == "file" and not include_files:
            continue
        if item.type == "directory" and not include_directories:
            continue

        # Check name filter
        if name_filter is not None and name_filter not in item.name:
            continue

        filtered_items.append(item)

    return filtered_items


def count_items_by_type(items: List[DirectoryItem]) -> Dict[str, int]:
    """
    统计目录项中文件和目录的数量

    Args:
        items: 目录项列表

    Returns:
        包含文件和目录数量的字典
    """
    counts = {"files": 0, "directories": 0}

    for item in items:
        if item.type == "file":
            counts["files"] += 1
        elif item.type == "directory":
            counts["directories"] += 1

    return counts