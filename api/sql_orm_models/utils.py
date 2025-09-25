from pathlib import Path
from datetime import datetime, timedelta, timezone
def parse_sql_file(file_path: str) -> dict[str, str]:
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
    result = {}
    current_title = None
    current_sql = []
    in_comment_block = False
    comment_block_lines : list[str] = []

    for line_str in lines:
        line = line_str.strip()

        if line.startswith("--"):
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

    return result

def now(utc_offset: int = 8):
    return datetime.now(tz=timezone(timedelta(hours=utc_offset)))

def now_str(utc_offset: int = 8):
    return now(utc_offset).strftime("%Y-%m-%d %H:%M:%S")

def datetime_from_timestamp_str(timestamp_str: str):
    return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")