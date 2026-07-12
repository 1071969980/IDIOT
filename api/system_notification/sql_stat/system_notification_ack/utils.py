"""系统级公告确认记录数据库操作"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import UUID as SQLTYPE_UUID

from api.sql_utils.utils import SQL_OP_ContextData, _resolve_conn, parse_sql_file

# 解析 SQL 文件
sql_file_path = Path(__file__).parent / "SystemNotificationAck.sql"
sql_statements = parse_sql_file(sql_file_path)

# SQL 语句常量
CREATE_TABLE = sql_statements.get_list("CreateTablesAndIndexes")  # list[str]
INSERT_ACK = sql_statements.get_str("InsertAck")
GET_UNACKED_NOTIFICATIONS = sql_statements.get_str("GetUnackedNotifications")
BULK_ACK_ALL_FOR_NEW_USER = sql_statements.get_str("BulkAckAllForNewUser")


@dataclass
class _SystemNotificationAckCreate:
    """创建系统公告确认记录的数据模型（不含 UUID 字段，由数据库生成）"""
    notification_id: UUID
    user_id: UUID


@dataclass
class _SystemNotificationResult:
    """系统公告查询结果（用于未 ACK 查询）"""
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


async def create_table(ctx: SQL_OP_ContextData | None = None) -> None:
    """创建表和索引"""
    async with _resolve_conn(ctx) as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        if ctx is None or ctx.auto_commit:
            await conn.commit()


async def insert_ack(
    data: _SystemNotificationAckCreate,
    ctx: SQL_OP_ContextData | None = None,
) -> Optional[UUID]:
    """插入 ACK 记录。ON CONFLICT DO NOTHING 保证幂等性。

    返回值：
    - UUID: 首次 ACK 成功，返回生成的记录 ID
    - None: 该用户已 ACK 过该公告（重复 ACK，幂等返回 None）
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(INSERT_ACK).bindparams(
                bindparam("notification_id", type_=SQLTYPE_UUID),
                bindparam("user_id", type_=SQLTYPE_UUID),
            ),
            {"notification_id": data.notification_id, "user_id": data.user_id},
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        row = result.first()
        return row.id if row else None


async def get_unacked_notifications(
    user_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> list[_SystemNotificationResult]:
    """获取用户未 ACK 的系统级公告列表（NOT EXISTS 子查询）"""
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(GET_UNACKED_NOTIFICATIONS).bindparams(
                bindparam("user_id", type_=SQLTYPE_UUID),
            ),
            {"user_id": user_id},
        )
        rows = result.fetchall()
        return [_row_to_record(row) for row in rows]


async def bulk_ack_all_for_new_user(
    user_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> int:
    """为新用户批量 ACK 所有历史系统公告，返回插入的记录数。"""
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(BULK_ACK_ALL_FOR_NEW_USER).bindparams(
                bindparam("user_id", type_=SQLTYPE_UUID),
            ),
            {"user_id": user_id},
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount
