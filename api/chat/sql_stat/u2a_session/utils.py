from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, Literal
from uuid import uuid4
from sqlalchemy import text, Row
from sqlalchemy.ext.asyncio import AsyncConnection

from api.sql_orm_models import ASYNC_SQL_ENGINE
from api.sql_orm_models.utils import parse_sql_file, now_str
from pathlib import Path


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
    id: int
    user_id: str
    session_id: str
    title: str
    archived: bool
    context_lock: bool
    created_at: str
    updated_at: str


@dataclass
class _U2ASessionCreate:
    """创建U2A会话的数据模型"""
    user_id: str
    session_id: Optional[str] = None
    title: Optional[str] = None
    archived: Optional[bool] = None
    context_lock: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class _U2ASessionUpdate:
    """更新U2A会话的数据模型"""
    session_id: str
    fields: Dict[
        Literal["user_id", "title", "archived", "context_lock", "created_at", "updated_at"],
        Union[str, bool]
    ]


async def create_table() -> None:
    """创建U2A会话表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(CREATE_TABLE))
        await conn.commit()


async def insert_session(session_data: _U2ASessionCreate) -> str:
    """插入新U2A会话

    Args:
        session_data: 会话创建数据

    Returns:
        新会话的session_id
    """
    if session_data.session_id is None:
        session_data.session_id = str(uuid4())
    if session_data.title is None:
        session_data.title = ""
    if session_data.archived is None:
        session_data.archived = False
    if session_data.context_lock is None:
        session_data.context_lock = False
    if session_data.created_at is None:
        session_data.created_at = now_str()
    if session_data.updated_at is None:
        session_data.updated_at = now_str()

    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(
            text(INSERT_SESSION),
            {
                "user_id": session_data.user_id,
                "session_id": session_data.session_id,
                "title": session_data.title
            }
        )
        await conn.commit()
        return session_data.session_id


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

    params = {"session_id_value": update_data.session_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0


async def session_exists(session_id: str) -> bool:
    """检查会话是否存在

    Args:
        session_id: 会话ID

    Returns:
        会话是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(IS_EXISTS), {"session_id_value": session_id})
        count = result.scalar()
        return count > 0


async def get_session(session_id: str) -> Optional[_U2ASession]:
    """获取会话信息

    Args:
        session_id: 会话ID

    Returns:
        会话信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION), {"session_id_value": session_id})
        row = result.first()

        if row is None:
            return None

        return _U2ASession(
            id=row.id,
            user_id=row.user_id,
            session_id=row.session_id,
            title=row.title,
            archived=row.archived,
            context_lock=row.context_lock,
            created_at=row.created_at,
            updated_at=row.updated_at
        )


async def get_sessions_by_user_id(user_id: str) -> list[_U2ASession]:
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
                session_id=row.session_id,
                title=row.title,
                archived=row.archived,
                context_lock=row.context_lock,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return sessions


async def get_session_field(
    session_id: str,
    field_name: Literal["id", "user_id", "session_id", "title", "archived", "context_lock", "created_at", "updated_at"]
) -> Optional[Union[int, str, bool]]:
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
            {"session_id_value": session_id, "field_name_1": field_name}
        )
        return result.scalar()


async def get_session_fields(
    session_id: str,
    field_names: list[Literal["id", "user_id", "session_id", "title", "archived", "context_lock", "created_at", "updated_at"]]
) -> Optional[Dict[
    Literal["id", "user_id", "session_id", "title", "archived", "context_lock", "created_at", "updated_at"],
    Union[int, str, bool]
]]:
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

    params = {"session_id_value": session_id}
    for i, field_name in enumerate(field_names, 1):
        params[f"field_name_{i}"] = field_name

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}


async def get_context_lock(session_id: str) -> Optional[bool]:
    """获取会话的context_lock状态

    Args:
        session_id: 会话ID

    Returns:
        context_lock状态，如果会话不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(GET_CONTEXT_LOCK), {"session_id_value": session_id})
        row = result.first()

        if row is None:
            return None

        return row.context_lock


async def update_context_lock(session_id: str, context_lock: bool) -> bool:
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
                "session_id_value": session_id,
                "context_lock_value": context_lock
            }
        )
        await conn.commit()
        return result.rowcount > 0


async def delete_session(session_id: str) -> bool:
    """删除会话

    Args:
        session_id: 会话ID

    Returns:
        删除是否成功（如果会话不存在，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_SESSION), {"session_id_value": session_id})
        await conn.commit()
        return result.rowcount > 0