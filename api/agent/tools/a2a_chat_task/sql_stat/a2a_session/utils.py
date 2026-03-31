from dataclasses import dataclass
from typing import Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file, now_str
from pathlib import Path


sql_file_path = Path(__file__).parent / "a2a_session.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements["CreateTable"]

INSERT_SESSION = sql_statements["InsertSession"]

IS_EXISTS = sql_statements["IsExists"]
QUERY_SESSION = sql_statements["QuerySession"]
QUERY_SESSION_BY_USER_A_ID = sql_statements["QuerySessionByUserAId"]
QUERY_SESSION_BY_USER_B_ID = sql_statements["QuerySessionByUserBId"]
QUERY_SESSIONS_BY_USER_ID = sql_statements["QuerySessionsByUserId"]
DELETE_SESSION = sql_statements["DeleteSession"]


@dataclass
class _A2ASession:
    """A2A会话数据模型 - 用户间会话"""
    id: UUID
    user_a_id: UUID
    user_b_id: UUID
    created_at: datetime
    updated_at: datetime


@dataclass
class _A2ASessionCreate:
    """创建A2A会话的数据模型"""
    user_a_id: UUID
    user_b_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None



async def create_table() -> None:
    """创建A2A会话表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stat in CREATE_TABLE:
            await conn.execute(text(stat))
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