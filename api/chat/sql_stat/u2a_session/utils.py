from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import now_str, parse_sql_file

sql_file_path = Path(__file__).parent / "U2ASession.sql"

sql_statements = parse_sql_file(sql_file_path)


CREATE_TABLE = sql_statements["CreateTable"]

INSERT_SESSION = sql_statements["InsertSession"]

UPDATE_SESSION1 = sql_statements["UpdateSession1"]
UPDATE_SESSION2 = sql_statements["UpdateSession2"]
UPDATE_SESSION3 = sql_statements["UpdateSession3"]

IS_EXISTS = sql_statements["IsExists"]
QUERY_SESSION = sql_statements["QuerySession"]
QUERY_SESSION_BY_USER_ID = sql_statements["QuerySessionByUserId"]
QUERY_FIELD1 = sql_statements["QueryField1"]
QUERY_FIELD2 = sql_statements["QueryField2"]
QUERY_FIELD3 = sql_statements["QueryField3"]
QUERY_FIELD4 = sql_statements["QueryField4"]
GET_CONTEXT_LOCK = sql_statements["GetContextLock"]
UPDATE_CONTEXT_LOCK = sql_statements["UpdateContextLock"]
DELETE_SESSION = sql_statements["DeleteSession"]


@dataclass
class _U2ASession:
    """U2A会话数据模型"""
    id: UUID
    user_id: UUID
    title: str
    archived: bool
    created_by: Literal["user", "agent"]
    context_lock: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class _U2ASessionCreate:
    """创建U2A会话的数据模型"""
    user_id: UUID
    title: str | None = None
    archived: bool | None = None
    created_by: Literal["user", "agent"] | None = None
    context_lock: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class _U2ASessionUpdate:
    """更新U2A会话的数据模型"""
    id: UUID
    fields: dict[
        Literal["user_id", "title", "archived", "created_by", "context_lock", "created_at", "updated_at"],
        UUID | str | bool,
    ]


async def create_table() -> None:
    """创建U2A会话表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_session(session_data: _U2ASessionCreate) -> UUID :
    """插入新U2A会话

    Args:
        session_data: 会话创建数据

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

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SESSION),
            {
                "user_id": session_data.user_id,
                "title": session_data.title,
                "created_by": session_data.created_by,
            },
        )
        await conn.commit()
        return result.scalar()


async def update_session_fields(update_data: _U2ASessionUpdate) -> bool:
    """更新会话字段

    Args:
        update_data: 会话更新数据

    Returns:
        更新是否成功
    """
    field_count = len(update_data.fields)

    if field_count == 0:
        return False
    elif field_count == 1:
        sql = UPDATE_SESSION1
    elif field_count == 2:
        sql = UPDATE_SESSION2
    elif field_count == 3:
        sql = UPDATE_SESSION3
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params: dict[str, Any] = {"id_value": update_data.id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        # replace sql stat string with field_name_i
        sql = sql.replace(f":field_name_{i}", field)
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0


async def session_exists(session_id: UUID) -> bool:
    """检查会话是否存在

    Args:
        session_id: 会话ID

    Returns:
        会话是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(IS_EXISTS), {"id_value": session_id})
        count = result.scalar()
        return count > 0


async def get_session(session_id: UUID) -> _U2ASession | None:
    """获取会话信息

    Args:
        session_id: 会话ID

    Returns:
        会话信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
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
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def get_sessions_by_user_id(user_id: UUID) -> list[_U2ASession]:
    """根据用户ID获取所有会话

    Args:
        user_id: 用户ID

    Returns:
        会话列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_BY_USER_ID), {"user_id_value": user_id})
        rows = result.fetchall()

        sessions = []
        for row in rows:
            sessions.append(_U2ASession(
                id=row.id,
                user_id=row.user_id,
                title=row.title,
                archived=row.archived,
                created_by=row.created_by,
                context_lock=row.context_lock,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ))

        return sessions


async def get_session_field(
    session_id: UUID,
    field_name: Literal["id", "user_id", "title", "archived", "created_by", "context_lock", "created_at", "updated_at"],
) -> UUID | str | bool | None:
    """获取会话的单个字段值

    Args:
        session_id: 会话ID
        field_name: 字段名

    Returns:
        字段值，如果会话不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_FIELD1),
            {"id_value": session_id, "field_name_1": field_name},
        )
        return result.scalar()


async def get_session_fields(
    session_id: UUID,
    field_names: list[Literal["id", "user_id", "title", "archived", "created_by", "context_lock", "created_at", "updated_at"]],
) -> dict[Literal["id", "user_id", "title", "archived", "created_by", "context_lock", "created_at", "updated_at"], UUID | str | bool] | None:
    """获取会话的多个字段值

    Args:
        session_id: 会话ID
        field_names: 字段名列表

    Returns:
        字段值字典，如果会话不存在则返回None
    """
    field_count = len(field_names)

    if field_count == 0:
        return {}
    elif field_count == 1:
        sql = QUERY_FIELD1
    elif field_count == 2:
        sql = QUERY_FIELD2
    elif field_count == 3:
        sql = QUERY_FIELD3
    elif field_count == 4:
        sql = QUERY_FIELD4
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"id_value": session_id}
    for i, field_name in enumerate(field_names, 1):
        sql = sql.replace(f":field_name_{i}", field_name)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}


async def get_context_lock(session_id: UUID) -> bool | None:
    """获取会话的context_lock状态

    Args:
        session_id: 会话ID

    Returns:
        context_lock状态，如果会话不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(GET_CONTEXT_LOCK), {"id_value": session_id})
        row = result.first()

        if row is None:
            return None

        return row.context_lock


async def update_context_lock(session_id: UUID, context_lock: bool) -> bool:
    """更新会话的context_lock状态

    Args:
        session_id: 会话ID
        context_lock: 新的context_lock状态

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_CONTEXT_LOCK),
            {
                "id_value": session_id,
                "context_lock_value": context_lock,
            },
        )
        await conn.commit()
        return result.rowcount > 0


async def delete_session(session_id: UUID) -> bool:
    """删除会话

    Args:
        session_id: 会话ID

    Returns:
        删除是否成功（如果会话不存在，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_SESSION), {"id_value": session_id})
        await conn.commit()
        return result.rowcount > 0
