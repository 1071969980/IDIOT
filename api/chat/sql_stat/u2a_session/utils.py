from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy import bindparam, text

from api.sql_utils.utils import SQL_OP_ContextData, _resolve_conn, now_str, parse_sql_file

sql_file_path = Path(__file__).parent / "U2ASession.sql"

sql_statements = parse_sql_file(sql_file_path)


CREATE_TABLE = sql_statements.get_list("CreateTable")
CREATE_SESSION_TRIGGERS = sql_statements.get_list("CreateSessionTriggers")

INSERT_SESSION = sql_statements.get_str("InsertSession")

UPDATE_SESSION_TITLE = sql_statements.get_str("UpdateSessionTitle")
IS_EXISTS = sql_statements.get_str("IsExists")
QUERY_SESSION = sql_statements.get_str("QuerySession")
QUERY_SESSION_BY_USER_ID = sql_statements.get_str("QuerySessionByUserId")
QUERY_SESSION_BY_CREATED_BY = sql_statements.get_str("QuerySessionByCreatedBy")
QUERY_LATEST_SESSION_BY_CREATED_BY = sql_statements.get_str("QueryLatestSessionByCreatedBy")
QUERY_SESSION_BY_CREATED_FROM_ID_BY_AGENT = sql_statements.get_str("QuerySessionByCreatedFromIdByAgent")
GET_CONTEXT_LOCK = sql_statements.get_str("GetContextLock")
UPDATE_CONTEXT_LOCK = sql_statements.get_str("UpdateContextLock")
DELETE_SESSION = sql_statements.get_str("DeleteSession")
DELETE_SESSIONS = sql_statements.get_str("DeleteSessions")


@dataclass
class _U2ASession:
    """U2A会话数据模型"""
    id: UUID
    user_id: UUID
    title: str
    archived: bool
    created_by: Literal["user", "agent", "system"]
    context_lock: bool
    created_from_id_by_agent: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass
class _U2ASessionCreate:
    """创建U2A会话的数据模型"""
    user_id: UUID
    title: str | None = None
    archived: bool | None = None
    created_by: Literal["user", "agent", "system"] | None = None
    context_lock: bool | None = None
    created_from_id_by_agent: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


async def create_table(ctx: SQL_OP_ContextData | None = None) -> None:
    """创建U2A会话表"""
    async with _resolve_conn(ctx) as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        for stmt in CREATE_SESSION_TRIGGERS:
            await conn.execute(text(stmt))
        if ctx is None or ctx.auto_commit:
            await conn.commit()


async def insert_session(
    session_data: _U2ASessionCreate,
    ctx: SQL_OP_ContextData | None = None,
) -> UUID:
    """插入新U2A会话

    Args:
        session_data: 会话创建数据
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        新会话的ID
    """
    if session_data.title is None:
        session_data.title = ""
    if session_data.archived is None:
        session_data.archived = False
    if session_data.created_by is None:
        session_data.created_by = "user"
    if session_data.context_lock is None:
        session_data.context_lock = False
    if session_data.created_at is None:
        session_data.created_at = now_str()
    if session_data.updated_at is None:
        session_data.updated_at = now_str()

    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(INSERT_SESSION),
            {
                "user_id": session_data.user_id,
                "title": session_data.title,
                "created_by": session_data.created_by,
                "created_from_id_by_agent": session_data.created_from_id_by_agent,
            },
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.scalar()


async def update_session_title(
    session_id: UUID,
    title: str,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """更新会话标题

    Args:
        session_id: 会话ID
        title: 新标题
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        更新是否成功
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_TITLE),
            {"id_value": session_id, "title_value": title},
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0


async def session_exists(
    session_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """检查会话是否存在

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        会话是否存在
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(IS_EXISTS), {"id_value": session_id})
        return result.scalar() > 0


async def get_session(
    session_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> _U2ASession | None:
    """获取会话信息

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        会话信息，如果不存在则返回None
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(QUERY_SESSION), {"id_value": session_id})
        row = result.first()
        if row is None:
            return None
        return _U2ASession(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            archived=row.archived,
            created_by=row.created_by,
            context_lock=row.context_lock,
            created_from_id_by_agent=row.created_from_id_by_agent,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def get_sessions_by_user_id(
    user_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> list[_U2ASession]:
    """根据用户ID获取所有会话

    Args:
        user_id: 用户ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        会话列表
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(QUERY_SESSION_BY_USER_ID), {"user_id_value": user_id})
        rows = result.fetchall()
        return [_U2ASession(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            archived=row.archived,
            created_by=row.created_by,
            context_lock=row.context_lock,
            created_from_id_by_agent=row.created_from_id_by_agent,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ) for row in rows]


async def get_context_lock(
    session_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> bool | None:
    """获取会话的context_lock状态

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        context_lock状态，如果会话不存在则返回None
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(GET_CONTEXT_LOCK), {"id_value": session_id})
        row = result.first()
        if row is None:
            return None
        return row.context_lock


async def update_context_lock(
    session_id: UUID,
    context_lock: bool,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """更新会话的context_lock状态

    Args:
        session_id: 会话ID
        context_lock: 新的context_lock状态
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        更新是否成功
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(UPDATE_CONTEXT_LOCK),
            {
                "id_value": session_id,
                "context_lock_value": context_lock,
            },
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0


async def delete_session(
    session_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """删除会话

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        删除是否成功（如果会话不存在，返回False）
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(DELETE_SESSION), {"id_value": session_id})
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0


async def delete_sessions(
    session_ids: list[UUID],
    ctx: SQL_OP_ContextData | None = None,
) -> int:
    """批量删除会话

    Args:
        session_ids: 会话ID列表
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        成功删除的会话数量
    """
    if not session_ids:
        return 0

    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(DELETE_SESSIONS).bindparams(
                bindparam("id_values", expanding=True),
            ),
            {"id_values": session_ids},
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount


async def get_sessions_by_created_by(
    user_id: UUID,
    created_by: Literal["user", "agent", "system"],
    ctx: SQL_OP_ContextData | None = None,
) -> list[_U2ASession]:
    """根据 created_by 角色检索 session

    Args:
        user_id: 用户 ID
        created_by: 创建者角色 ("user", "agent", "system")
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        会话列表
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(QUERY_SESSION_BY_CREATED_BY), {"created_by_value": created_by, "user_id_value": user_id})
        rows = result.fetchall()
        return [_U2ASession(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            archived=row.archived,
            created_by=row.created_by,
            context_lock=row.context_lock,
            created_from_id_by_agent=row.created_from_id_by_agent,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ) for row in rows]


async def get_latest_session_by_created_by(
    user_id: UUID,
    created_by: Literal["user", "agent", "system"],
    ctx: SQL_OP_ContextData | None = None,
) -> _U2ASession | None:
    """获取用户指定 created_by 的最新会话（按 created_at 降序）

    Args:
        user_id: 用户 ID
        created_by: 创建者角色 ("user", "agent", "system")
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        最新的会话，如果不存在则返回 None
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(QUERY_LATEST_SESSION_BY_CREATED_BY),
            {"user_id_value": user_id, "created_by_value": created_by}
        )
        row = result.first()
        if row is None:
            return None
        return _U2ASession(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            archived=row.archived,
            created_by=row.created_by,
            context_lock=row.context_lock,
            created_from_id_by_agent=row.created_from_id_by_agent,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def get_sessions_by_created_from_id(
    parent_session_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> list[_U2ASession]:
    """根据 created_from_id_by_agent 检索子 session（父子关系检索）

    Args:
        parent_session_id: 父 session ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        子 session 列表
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(QUERY_SESSION_BY_CREATED_FROM_ID_BY_AGENT), {"created_from_id_by_agent_value": parent_session_id})
        rows = result.fetchall()
        return [_U2ASession(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            archived=row.archived,
            created_by=row.created_by,
            context_lock=row.context_lock,
            created_from_id_by_agent=row.created_from_id_by_agent,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ) for row in rows]
