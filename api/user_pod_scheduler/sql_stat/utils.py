"""用户 Pod 记录数据库操作"""

from dataclasses import dataclass
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# 解析 SQL 文件
sql_file_path = Path(__file__).parent / "UserPodRecord.sql"
sql_statements = parse_sql_file(sql_file_path)

# SQL 语句常量
CREATE_TABLE = sql_statements["CreateTable"]
INSERT_RECORD = sql_statements["InsertRecord"]
QUERY_RECORD_BY_USER_ID = sql_statements["QueryRecordByUserId"]
QUERY_RECORD_BY_ID = sql_statements["QueryRecordById"]
UPDATE_HEARTBEAT = sql_statements["UpdateHeartbeat"]
UPDATE_STATUS = sql_statements["UpdateStatus"]
UPDATE_STATUS_AND_UNLOAD = sql_statements["UpdateStatusAndUnload"]
QUERY_TIMEOUT_RECORDS = sql_statements["QueryTimeoutRecords"]
QUERY_ALL_RUNNING_RECORDS = sql_statements["QueryAllRunningRecords"]
DELETE_RECORD_BY_USER_ID = sql_statements["DeleteRecordByUserId"]
QUERY_RECORD_LIFETIME = sql_statements["QueryRecordLifetime"]


@dataclass
class _UserPodRecord:
    """用户 Pod 记录数据模型

    该数据模型尽量不应该被其他模块直接存储或长期持有。
    """
    id: UUID
    user_id: UUID
    status: str
    create_at: datetime
    heartbeat_at: datetime
    unload_at: Optional[datetime]
    error_message: Optional[str]
    pod_name: str
    namespace: str


@dataclass
class _UserPodRecordCreate:
    """创建用户 Pod 记录的数据模型"""
    user_id: UUID
    status: str
    pod_name: str
    namespace: str = "idiot-user-space"


@dataclass
class _UserPodRecordLifetime:
    """用户 Pod 生存时间记录"""
    id: UUID
    user_id: UUID
    status: str
    create_at: datetime
    heartbeat_at: datetime
    unload_at: Optional[datetime]
    lifetime_seconds: float


def _row_to_record(row) -> _UserPodRecord:
    """将数据库行转换为记录模型"""
    return _UserPodRecord(
        id=row.id,
        user_id=row.user_id,
        status=row.status,
        create_at=row.create_at,
        heartbeat_at=row.heartbeat_at,
        unload_at=row.unload_at,
        error_message=row.error_message,
        pod_name=row.pod_name,
        namespace=row.namespace,
    )


def _row_to_lifetime(row) -> _UserPodRecordLifetime:
    """将数据库行转换为生存时间模型"""
    return _UserPodRecordLifetime(
        id=row.id,
        user_id=row.user_id,
        status=row.status,
        create_at=row.create_at,
        heartbeat_at=row.heartbeat_at,
        unload_at=row.unload_at,
        lifetime_seconds=row.lifetime_seconds,
    )


async def create_table() -> None:
    """创建表和索引"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_record(record_data: _UserPodRecordCreate) -> UUID:
    """插入新记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_RECORD),
            {
                "user_id": record_data.user_id,
                "status": record_data.status,
                "pod_name": record_data.pod_name,
                "namespace": record_data.namespace,
            }
        )
        await conn.commit()
        return result.scalar()


async def query_record_by_user_id(user_id: UUID) -> Optional[_UserPodRecord]:
    """根据用户ID查询记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_RECORD_BY_USER_ID),
            {"user_id_value": user_id}
        )
        row = result.first()
        return _row_to_record(row) if row else None


async def query_record_by_id(record_id: UUID) -> Optional[_UserPodRecord]:
    """根据记录ID查询记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_RECORD_BY_ID),
            {"id_value": record_id}
        )
        row = result.first()
        return _row_to_record(row) if row else None


async def update_heartbeat(user_id: UUID) -> bool:
    """更新心跳时间"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_HEARTBEAT),
            {"user_id_value": user_id}
        )
        await conn.commit()
        return result.rowcount > 0


async def update_status(user_id: UUID, status: str, error_message: Optional[str] = None) -> bool:
    """更新状态"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_STATUS),
            {"user_id_value": user_id, "status_value": status, "error_message_value": error_message}
        )
        await conn.commit()
        return result.rowcount > 0


async def update_status_and_unload(user_id: UUID, status: str, error_message: Optional[str] = None) -> bool:
    """更新状态并记录卸载时间"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_STATUS_AND_UNLOAD),
            {"user_id_value": user_id, "status_value": status, "error_message_value": error_message}
        )
        await conn.commit()
        return result.rowcount > 0


async def query_timeout_records(heartbeat_threshold: datetime) -> List[_UserPodRecord]:
    """查询心跳超时的记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_TIMEOUT_RECORDS),
            {"heartbeat_threshold": heartbeat_threshold}
        )
        return [_row_to_record(row) for row in result.fetchall()]


async def query_all_running_records() -> List[_UserPodRecord]:
    """查询所有运行中的记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_ALL_RUNNING_RECORDS))
        return [_row_to_record(row) for row in result.fetchall()]


async def delete_record_by_user_id(user_id: UUID) -> bool:
    """删除记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_RECORD_BY_USER_ID),
            {"user_id_value": user_id}
        )
        await conn.commit()
        return result.rowcount > 0


async def query_record_lifetime(user_id: UUID) -> Optional[_UserPodRecordLifetime]:
    """查询记录生存时间"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_RECORD_LIFETIME),
            {"user_id_value": user_id}
        )
        row = result.first()
        return _row_to_lifetime(row) if row else None