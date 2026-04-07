from pathlib import Path
from datetime import datetime, timedelta, timezone


class SqlStatements(dict[str, str | list[str]]):
    """Typed wrapper for parsed SQL statements with explicit get methods."""

    def get_str(self, key: str) -> str:
        """Get a single SQL statement by key.

        Raises:
            TypeError: if the value is a list.
        """
        value = self[key]
        if isinstance(value, list):
            raise TypeError(
                f"SQL statement '{key}' is a list, not a single statement. Use get_list() instead."
            )
        return value

    def get_list(self, key: str) -> list[str]:
        """Get a list of SQL statements by key.

        Raises:
            TypeError: if the value is a single string.
        """
        value = self[key]
        if isinstance(value, str):
            raise TypeError(
                f"SQL statement '{key}' is a single statement, not a list. Use get_str() instead."
            )
        return value


def parse_sql_file(file_path: str | Path) -> SqlStatements:
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
    raw_result: dict[str, str] = {}
    current_title = None
    current_sql: list[str] = []
    in_comment_block = False
    comment_block_lines: list[str] = []

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
                        raw_result[current_title] = "\n".join(current_sql).strip()
                        current_sql = []

                    current_title = comment_block_lines[-1][2:].strip()  # Remove '--' prefix

                in_comment_block = False
                comment_block_lines = []

            # Add non-empty SQL lines
            if line:
                current_sql.append(line)

    # Add the last SQL statement
    if current_title and current_sql:
        raw_result[current_title] = "\n".join(current_sql).strip()

    # Post-process: split multi-statement blocks (separated by --\n) and build result
    result = SqlStatements()
    for k, v in raw_result.items():
        stmts = [stmt.strip() for stmt in v.split("--\n") if stmt.strip()]
        result[k] = stmts[0] if len(stmts) == 1 else stmts

    return result

def now(utc_offset: int = 8):
    return datetime.now(tz=timezone(timedelta(hours=utc_offset)))

def now_str(utc_offset: int = 8):
    return now(utc_offset).strftime("%Y-%m-%d %H:%M:%S")

def datetime_from_timestamp_str(timestamp_str: str):
    return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
