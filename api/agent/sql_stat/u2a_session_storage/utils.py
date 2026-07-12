import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as SQLTYPE_UUID

from api.redis.distributed_lock import RedisDistributedLock
from api.redis.lock_names import LockNames
from api.sql_utils.utils import SQL_OP_ContextData, _resolve_conn, parse_sql_file

# Parse SQL file to get SQL statements
sql_statements = parse_sql_file(Path(__file__).parent / "u2a_session_storage.sql")


# Extract SQL statements
CREATE_U2A_SESSION_STORAGE_TABLE = sql_statements.get_list("CreateU2ASessionStorageTable")
INSERT_SESSION_STORAGE = sql_statements.get_str("InsertSessionStorage")
UPDATE_SESSION_STORAGE_BY_ID = sql_statements.get_str("UpdateSessionStorageById")
UPDATE_SESSION_STORAGE_BY_SESSION_ID = sql_statements.get_str("UpdateSessionStorageBySessionId")
QUERY_SESSION_STORAGE_BY_ID = sql_statements.get_str("QuerySessionStorageById")
QUERY_SESSION_STORAGE_BY_SESSION_ID = sql_statements.get_str("QuerySessionStorageBySessionId")
DELETE_SESSION_STORAGE_BY_ID = sql_statements.get_str("DeleteSessionStorageById")
DELETE_SESSION_STORAGE_BY_SESSION_ID = sql_statements.get_str("DeleteSessionStorageBySessionId")
SESSION_STORAGE_EXISTS_BY_ID = sql_statements.get_str("SessionStorageExistsById")
SESSION_STORAGE_EXISTS_BY_SESSION_ID = sql_statements.get_str("SessionStorageExistsBySessionId")


@dataclass
class _U2ASessionStorage:
    """U2A会话存储数据模型，用于保存多轮对话之间的临时状态和变量"""
    id: UUID
    session_id: UUID
    storage: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class _U2ASessionStorageCreate:
    """创建U2A会话存储的数据模型"""
    session_id: UUID
    storage: dict[str, Any]


@dataclass
class _U2ASessionStorageUpdate:
    """更新U2A会话存储的数据模型"""
    id: UUID | None = None
    session_id: UUID | None = None
    storage: dict[str, Any] | None = None


async def create_table(ctx: SQL_OP_ContextData | None = None) -> None:
    """确保表存在"""
    async with _resolve_conn(ctx) as conn:
        for stat in CREATE_U2A_SESSION_STORAGE_TABLE:
            await conn.execute(text(stat))
        if ctx is None or ctx.auto_commit:
            await conn.commit()


async def insert_session_storage(
    storage_data: _U2ASessionStorageCreate,
    ctx: SQL_OP_ContextData | None = None,
) -> UUID:
    """插入新的会话存储

    Args:
        storage_data: 会话存储创建数据
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        新创建的存储ID
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(INSERT_SESSION_STORAGE).bindparams(
                bindparam("session_id", type_=SQLTYPE_UUID),
                bindparam("storage", type_=JSONB),
            ),
            {
                "session_id": storage_data.session_id,
                "storage": storage_data.storage,
            },
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.scalar()


async def get_session_storage_by_id(
    storage_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> _U2ASessionStorage | None:
    """根据ID获取会话存储

    Args:
        storage_id: 存储ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        会话存储对象, 如果不存在返回None
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(QUERY_SESSION_STORAGE_BY_ID),
            {"id_value": storage_id},
        )
        row = result.first()

        if row is None:
            return None

        return _U2ASessionStorage(
            id=row.id,
            session_id=row.session_id,
            storage=(
                json.loads(row.storage)
                if isinstance(row.storage, str)
                else row.storage
            ),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def get_session_storage_by_session_id(
    session_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> _U2ASessionStorage | None:
    """根据会话ID获取会话存储

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        会话存储对象, 如果不存在返回None
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(QUERY_SESSION_STORAGE_BY_SESSION_ID),
            {"session_id_value": session_id},
        )
        row = result.first()

        if row is None:
            return None

        return _U2ASessionStorage(
            id=row.id,
            session_id=row.session_id,
            storage=(
                json.loads(row.storage)
                if isinstance(row.storage, str)
                else row.storage
            ),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def update_session_storage_by_id(
    storage_id: UUID,
    storage: dict[str, Any],
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """更新会话存储

    Args:
        storage_id: 存储ID
        storage: 新的存储数据
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        更新是否成功
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_STORAGE_BY_ID).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
                bindparam("storage", type_=JSONB),
            ),
            {
                "id_value": storage_id,
                "storage": storage,
            },
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0


async def update_session_storage_by_session_id(
    session_id: UUID, storage: dict[str, Any],
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """根据会话ID更新会话存储（UPSERT语义，如果不存在则创建）

    Args:
        session_id: 会话ID
        storage: 新的存储数据
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        操作是否成功
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_STORAGE_BY_SESSION_ID).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
                bindparam("storage", type_=JSONB),
            ),
            {
                "session_id_value": session_id,
                "storage": storage,
            },
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0


async def delete_session_storage_by_id(storage_id: UUID, ctx: SQL_OP_ContextData | None = None) -> bool:
    """删除会话存储

    Args:
        storage_id: 存储ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        删除是否成功
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(DELETE_SESSION_STORAGE_BY_ID),
            {"id_value": storage_id},
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0


async def delete_session_storage_by_session_id(session_id: UUID, ctx: SQL_OP_ContextData | None = None) -> bool:
    """根据会话ID删除会话存储

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        删除是否成功
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(DELETE_SESSION_STORAGE_BY_SESSION_ID),
            {"session_id_value": session_id},
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0


async def session_storage_exists_by_id(storage_id: UUID, ctx: SQL_OP_ContextData | None = None) -> bool:
    """检查会话存储是否存在

    Args:
        storage_id: 存储ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        存储是否存在
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(SESSION_STORAGE_EXISTS_BY_ID),
            {"id_value": storage_id},
        )
        return result.scalar()


async def session_storage_exists_by_session_id(session_id: UUID, ctx: SQL_OP_ContextData | None = None) -> bool:
    """根据会话ID检查会话存储是否存在

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        存储是否存在
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(SESSION_STORAGE_EXISTS_BY_SESSION_ID),
            {"session_id_value": session_id},
        )
        return result.scalar()


@asynccontextmanager
async def u2a_session_storage_lock(
    session_id: UUID,
    timeout: float = 30,
    auto_renewal: bool = True,
):
    """
    Session Storage 并发访问锁的上下文管理器

    使用 Redis 分布式锁保护对 Session Storage 的并发访问，
    防止 Read-Modify-Write 竞争条件导致的数据丢失。

    **锁的语义**：
    - 锁粒度：Session 级别（锁住整个 storage 对象）
    - 不同 Session 之间不会互相阻塞
    - 同一 Session 的所有操作串行化

    **并发规则**：
    - 同一 Session 的锁：互斥 ❌
    - 不同 Session 的锁：并发 ✅

    Args:
        session_id: 会话 ID，用于构造锁的键名
        timeout: 锁的超时时间（秒），默认 30 秒
        auto_renewal: 是否自动续期，默认 True

    Yields:
        None: 上下文管理器不返回值，仅用于临界区保护

    Raises:
        RuntimeError: 获取锁失败或 Redis 连接错误

    Example:
        async with u2a_session_storage_lock(session_id):
            storage = await get_session_storage_by_session_id(session_id)
            storage["field1"] = "value1"
            storage["todos"].append(new_todo)
            await update_session_storage_by_session_id(session_id, storage)
    """
    lock_key = LockNames.u2a_session_storage(session_id)
    lock = RedisDistributedLock(
        key=lock_key,
        timeout=timeout,
        auto_renewal=auto_renewal,
    )

    async with lock:
        yield
