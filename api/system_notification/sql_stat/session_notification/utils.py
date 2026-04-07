"""会话级公告数据库操作"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# 解析 SQL 文件
sql_file_path = Path(__file__).parent / "SessionNotification.sql"
sql_statements = parse_sql_file(sql_file_path)

# SQL 语句常量
CREATE_TABLE = sql_statements.get_list("CreateTablesAndIndexes")  # list[str]
INSERT_NOTIFICATION = sql_statements.get_str("InsertNotification")
GET_ACTIVE_BY_SESSION_ID = sql_statements.get_str("GetActiveBySessionId")
SOFT_DELETE = sql_statements.get_str("SoftDelete")


@dataclass
class _SessionNotificationCreate:
    """创建会话级公告的数据模型（不含 UUID 字段，由数据库生成）"""
    session_id: UUID
    user_id: UUID
    level: str
    content: str


@dataclass
class _SessionNotificationResult:
    """会话级公告查询结果"""
    id: UUID
    session_id: UUID
    user_id: UUID
    level: str
    content: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]


def _row_to_record(row) -> _SessionNotificationResult:
    """将数据库行转换为会话级公告记录模型"""
    return _SessionNotificationResult(
        id=row.id,
        session_id=row.session_id,
        user_id=row.user_id,
        level=row.level,
        content=row.content,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


async def create_table() -> None:
    """创建表、索引和触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_session_notification(
    data: _SessionNotificationCreate,
) -> _SessionNotificationResult:
    """插入会话级公告，返回完整记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_NOTIFICATION),
            {
                "session_id": data.session_id,
                "user_id": data.user_id,
                "level": data.level,
                "content": data.content,
            },
        )
        await conn.commit()
        row = result.first()
        return _row_to_record(row)


async def get_active_by_session_id(
    session_id: UUID,
) -> list[_SessionNotificationResult]:
    """获取会话的未删除会话级公告列表。session_id 已关联唯一用户，只需 session_id 参数。"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_ACTIVE_BY_SESSION_ID),
            {"session_id": session_id},
        )
        rows = result.fetchall()
        return [_row_to_record(row) for row in rows]


async def soft_delete(
    notification_id: UUID,
    session_id: UUID,
) -> bool:
    """软删除会话级公告。同时校验 session_id 确保归属关系正确。返回是否成功删除。"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(SOFT_DELETE),
            {"notification_id": notification_id, "session_id": session_id},
        )
        await conn.commit()
        return result.rowcount > 0
