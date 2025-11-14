from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Union
from uuid import UUID
def parse_sql_file(file_path: str | Path) -> dict[str, str | list[str]]:
    """
    Parse SQL file by comment blocks, where the last line of each comment block
    is the title for the SQL statement that follows.

    Args:
        file_path: Path to the SQL file

    Returns:
        Dictionary mapping titles to SQL statements
    """
    with Path(file_path).open("r", encoding="utf-8") as f:
        content = f.read()

    # Split by comment blocks (lines starting with --)
    lines = content.split("\n")
    result: dict[str, str | list[str]] = {}
    current_title = None
    current_sql = []
    in_comment_block = False
    comment_block_lines : list[str] = []

    for line_str in lines:
        line = line_str.strip()

        if not line:
            continue

        if line.startswith("--") and line != "--":
            # This is a comment line
            in_comment_block = True
            comment_block_lines.append(line)
        else:
            if in_comment_block:
                # We just finished a comment block, the last comment line is the title
                if comment_block_lines:
                    # Clear previous SQL if we have a new title
                    if current_title and current_sql:
                        result[current_title] = "\n".join(current_sql).strip()
                        current_sql = []

                    current_title = comment_block_lines[-1][2:].strip()  # Remove '--' prefix

                in_comment_block = False
                comment_block_lines = []

            # Add non-empty SQL lines
            if line:
                current_sql.append(line)

    # Add the last SQL statement
    if current_title and current_sql:
        result[current_title] = "\n".join(current_sql).strip()

    for k,v in result.items():
        # split sql statement with --\n
        result[k] = [stmt.strip() for stmt in v.split("--\n") if stmt.strip()]
        if isinstance(result[k], list) and len(result[k]) == 1:
            result[k] = result[k][0]

    return result

def format_list_for_sql(items: list[str | UUID | int | Any]) -> str:
    """
    将Python列表转换为SQL语句中可用的字符串格式

    Args:
        items: 包含UUID、字符串、整数等的Python列表

    Returns:
        格式化后的字符串，适用于SQL IN子句或其他需要列表的场景

    Examples:
        >>> format_list_for_sql([UUID('123'), UUID('456')])
        "123-..., 456-..."

        >>> format_list_for_sql([1, 2, 3])
        "1, 2, 3"

        >>> format_list_for_sql(["hello", "world"])
        "'hello', 'world'"
    """
    if not items:
        return ""

    formatted_items = []
    for item in items:
        if isinstance(item, str):
            formatted_items.append(f"'{item}'")
        elif isinstance(item, UUID):
            formatted_items.append(f"{item}")
        elif isinstance(item, int):
            formatted_items.append(str(item))
        else:
            # 对于其他类型，直接转换为字符串并加上单引号
            formatted_items.append(f"'{str(item)}'")

    return ", ".join(formatted_items)

def format_list_for_sql_array(items: list[str | UUID | int | Any]) -> str:
    return f"{{{format_list_for_sql(items)}}}" # ret like "{item1, item2, item3}"

def now(utc_offset: int = 8):
    return datetime.now(tz=timezone(timedelta(hours=utc_offset)))

def now_str(utc_offset: int = 8):
    return now(utc_offset).strftime("%Y-%m-%d %H:%M:%S")

def datetime_from_timestamp_str(timestamp_str: str):
    return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")