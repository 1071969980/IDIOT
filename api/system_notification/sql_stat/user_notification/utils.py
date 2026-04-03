"""用户级公告数据库操作"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# 解析 SQL 文件
sql_file_path = Path(__file__).parent / "UserNotification.sql"
sql_statements = parse_sql_file(sql_file_path)

# SQL 语句常量
CREATE_TABLE = sql_statements["CreateTablesAndIndexes"]  # list[str]
INSERT_NOTIFICATION = sql_statements["InsertNotification"]
GET_ACTIVE_BY_USER_ID = sql_statements["GetActiveByUserId"]
SOFT_DELETE = sql_statements["SoftDelete"]


@dataclass
class _UserNotificationCreate:
    """创建用户级公告的数据模型（不含 UUID 字段，由数据库生成）"""
    user_id: UUID
    level: str
    content: str


@dataclass
class _UserNotificationResult:
    """用户级公告查询结果"""
    id: UUID
    user_id: UUID
    level: str
    content: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]


def _row_to_record(row) -> _UserNotificationResult:
    """将数据库行转换为用户级公告记录模型"""
    return _UserNotificationResult(
        id=row.id,
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


async def insert_user_notification(
    data: _UserNotificationCreate,
) -> _UserNotificationResult:
    """插入用户级公告，返回完整记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_NOTIFICATION),
            {"user_id": data.user_id, "level": data.level, "content": data.content},
        )
        await conn.commit()
        row = result.first()
        return _row_to_record(row)


async def get_active_by_user_id(
    user_id: UUID,
) -> list[_UserNotificationResult]:
    """获取用户的未删除用户级公告列表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_ACTIVE_BY_USER_ID),
            {"user_id": user_id},
        )
        rows = result.fetchall()
        return [_row_to_record(row) for row in rows]


async def soft_delete(
    notification_id: UUID,
    user_id: UUID,
) -> bool:
    """软删除用户级公告。返回是否成功删除。"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(SOFT_DELETE),
            {"notification_id": notification_id, "user_id": user_id},
        )
        await conn.commit()
        return result.rowcount > 0
