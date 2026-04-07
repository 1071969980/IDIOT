"""系统级公告数据库操作"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# 解析 SQL 文件
sql_file_path = Path(__file__).parent / "SystemNotification.sql"
sql_statements = parse_sql_file(sql_file_path)

# SQL 语句常量
CREATE_TABLE = sql_statements["CreateTablesAndIndexes"]  # list[str]
INSERT_NOTIFICATION = sql_statements["InsertNotification"]
GET_ALL_NOTIFICATIONS = sql_statements["GetAllNotifications"]


@dataclass
class _SystemNotificationCreate:
    """创建系统公告的数据模型（不含 UUID 字段，由数据库生成）"""
    level: str
    content: str


@dataclass
class _SystemNotificationResult:
    """系统公告查询结果"""
    id: UUID
    level: str
    content: str
    created_at: datetime
    updated_at: datetime


def _row_to_record(row) -> _SystemNotificationResult:
    """将数据库行转换为系统公告记录模型"""
    return _SystemNotificationResult(
        id=row.id,
        level=row.level,
        content=row.content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_table() -> None:
    """创建表、索引和触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_notification(
    data: _SystemNotificationCreate,
) -> _SystemNotificationResult:
    """插入系统公告，返回完整记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_NOTIFICATION),
            {"level": data.level, "content": data.content},
        )
        await conn.commit()
        row = result.first()
        return _row_to_record(row)


async def get_all_notifications(
    limit: int = 100,
    offset: int = 0,
) -> list[_SystemNotificationResult]:
    """获取所有系统公告（管理端分页查询）"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_ALL_NOTIFICATIONS),
            {"limit": limit, "offset": offset},
        )
        rows = result.fetchall()
        return [_row_to_record(row) for row in rows]
