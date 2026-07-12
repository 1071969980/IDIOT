from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any

from api.sql_utils.constant import ASYNC_SQL_ENGINE


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


@asynccontextmanager
async def _resolve_conn(ctx: "SQL_OP_ContextData | None"):
    """解析数据库连接：有 ctx 则共享其连接，无 ctx 则自建并管理生命周期。

    Yields:
        数据库连接对象。
    """
    if ctx is not None:
        yield ctx.conn
    else:
        async with ASYNC_SQL_ENGINE.connect() as conn:
            yield conn


@dataclass
class SQL_OP_ContextData:
    """数据库操作上下文，支持连接共享与事务控制。

    使多个 SQL 工具函数共享同一连接，实现多操作原子事务。

    用法::

        # 多操作原子事务（手动提交）
        ctx = SQL_OP_ContextData(description="create session with branch")
        async with ctx:
            session_id = await insert_session(data, ctx)
            await insert_branch(branch_data, ctx)
            await ctx.commit()  # 手动一次性提交

        # 自动提交模式（每个操作独立提交）
        ctx = SQL_OP_ContextData(auto_commit=True, description="auto mode")
        async with ctx:
            await insert_session(data, ctx)      # 自动提交
            await update_title(id, title, ctx)    # 自动提交

        # 异常时自动回滚（不调用 commit，__aexit__ 关闭连接即回滚）
        ctx = SQL_OP_ContextData(description="atomic batch")
        async with ctx:
            await insert_session(data1, ctx)
            await insert_session(data2, ctx)
            # 如果这里抛异常，连接关闭时自动回滚
            await ctx.commit()

    Attributes:
        auto_commit: 是否在每个操作后自动提交。默认 False，由调用方控制提交时机。
        description: 可选的描述字符串，用于调试/追踪。
    """

    _conn: Any = field(default=None, repr=False)
    auto_commit: bool = False
    description: str = ""

    @property
    def conn(self) -> Any:
        """获取数据库连接。

        Raises:
            RuntimeError: 如果连接尚未初始化（未使用 ``async with ctx:`` 进入上下文）。
        """
        if self._conn is None:
            raise RuntimeError(
                f"数据库连接未初始化。请使用 'async with SQL_OP_ContextData(...)' 上下文管理器。"
                f" 描述: {self.description!r}"
            )
        return self._conn

    async def __aenter__(self) -> "SQL_OP_ContextData":
        self._conn = await ASYNC_SQL_ENGINE.connect().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn is not None:
            await self._conn.close()

    async def commit(self) -> None:
        """提交当前事务。"""
        if self._conn is not None:
            await self._conn.commit()

    async def rollback(self) -> None:
        """回滚当前事务。"""
        if self._conn is not None:
            await self._conn.rollback()
