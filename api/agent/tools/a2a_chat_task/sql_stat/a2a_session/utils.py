from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, Literal
from uuid import UUID
from sqlalchemy import text, Row
from sqlalchemy.ext.asyncio import AsyncConnection

from api.sql_orm_models import ASYNC_SQL_ENGINE
from api.sql_orm_models.utils import parse_sql_file, now_str
from pathlib import Path


sql_file_path = Path(__file__).parent / "a2a_session.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements["CreateTable"]

INSERT_SESSION = sql_statements["InsertSession"]

UPDATE_SESSION1 = sql_statements["UpdateSession1"]
UPDATE_SESSION2 = sql_statements["UpdateSession2"]
UPDATE_SESSION3 = sql_statements["UpdateSession3"]

IS_EXISTS = sql_statements["IsExists"]
QUERY_SESSION = sql_statements["QuerySession"]
QUERY_SESSION_BY_USER_A_ID = sql_statements["QuerySessionByUserAId"]
QUERY_SESSION_BY_USER_B_ID = sql_statements["QuerySessionByUserBId"]
QUERY_SESSIONS_BY_USER_ID = sql_statements["QuerySessionsByUserId"]
QUERY_FIELD1 = sql_statements["QueryField1"]
QUERY_FIELD2 = sql_statements["QueryField2"]
QUERY_FIELD3 = sql_statements["QueryField3"]
QUERY_FIELD4 = sql_statements["QueryField4"]
QUERY_FIELD5 = sql_statements["QueryField5"]
DELETE_SESSION = sql_statements["DeleteSession"]


@dataclass
class _A2ASession:
    """A2A会话数据模型 - 用户间会话"""
    id: UUID
    user_a_id: UUID
    user_b_id: UUID
    created_at: str
    updated_at: str


@dataclass
class _A2ASessionCreate:
    """创建A2A会话的数据模型"""
    user_a_id: UUID
    user_b_id: UUID
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class _A2ASessionUpdate:
    """更新A2A会话的数据模型"""
    id: UUID
    fields: Dict[
        Literal["user_a_id", "user_b_id", "created_at", "updated_at"],
        Union[UUID, str]
    ]


async def create_table() -> None:
    """创建A2A会话表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(CREATE_TABLE))
        await conn.commit()


async def insert_session(session_data: _A2ASessionCreate) -> UUID:
    """插入新A2A会话

    Args:
        session_data: 会话创建数据

    Returns:
        新会话的ID
    """
    if session_data.created_at is None:
        session_data.created_at = now_str()
    if session_data.updated_at is None:
        session_data.updated_at = now_str()

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SESSION),
            {
                "user_a_id": session_data.user_a_id,
                "user_b_id": session_data.user_b_id
            }
        )
        await conn.commit()
        return result.scalar()


async def update_session_fields(update_data: _A2ASessionUpdate) -> bool:
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

    params = {"id_value": update_data.id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
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


async def get_session(session_id: UUID) -> Optional[_A2ASession]:
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

        return _A2ASession(
            id=row.id,
            user_a_id=row.user_a_id,
            user_b_id=row.user_b_id,
            created_at=row.created_at,
            updated_at=row.updated_at
        )


async def get_sessions_by_user_a_id(user_a_id: UUID) -> list[_A2ASession]:
    """根据用户A ID获取所有会话

    Args:
        user_a_id: 用户A ID

    Returns:
        会话列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_BY_USER_A_ID), {"user_a_id_value": user_a_id})
        rows = result.fetchall()

        sessions = []
        for row in rows:
            sessions.append(_A2ASession(
                id=row.id,
                user_a_id=row.user_a_id,
                user_b_id=row.user_b_id,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return sessions


async def get_sessions_by_user_b_id(user_b_id: UUID) -> list[_A2ASession]:
    """根据用户B ID获取所有会话

    Args:
        user_b_id: 用户B ID

    Returns:
        会话列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_BY_USER_B_ID), {"user_b_id_value": user_b_id})
        rows = result.fetchall()

        sessions = []
        for row in rows:
            sessions.append(_A2ASession(
                id=row.id,
                user_a_id=row.user_a_id,
                user_b_id=row.user_b_id,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return sessions


async def get_sessions_by_user_id(user_id: UUID) -> list[_A2ASession]:
    """根据用户ID获取所有相关会话（作为用户A或用户B）

    Args:
        user_id: 用户ID

    Returns:
        会话列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSIONS_BY_USER_ID), {"user_id_value": user_id})
        rows = result.fetchall()

        sessions = []
        for row in rows:
            sessions.append(_A2ASession(
                id=row.id,
                user_a_id=row.user_a_id,
                user_b_id=row.user_b_id,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return sessions


async def get_session_field(
    session_id: UUID,
    field_name: Literal["id", "user_a_id", "user_b_id", "created_at", "updated_at"]
) -> Optional[Union[UUID, str]]:
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
            {"id_value": session_id, "field_name_1": field_name}
        )
        return result.scalar()


async def get_session_fields(
    session_id: UUID,
    field_names: list[Literal["id", "user_a_id", "user_b_id", "created_at", "updated_at"]]
) -> Optional[Dict[
    Literal["id", "user_a_id", "user_b_id", "created_at", "updated_at"],
    Union[UUID, str]
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
    elif field_count == 5:
        sql = QUERY_FIELD5
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"id_value": session_id}
    for i, field_name in enumerate(field_names, 1):
        params[f"field_name_{i}"] = field_name

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}


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