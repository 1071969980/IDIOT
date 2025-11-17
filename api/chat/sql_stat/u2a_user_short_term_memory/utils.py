from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Union, Any
from uuid import UUID

from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import ARRAY, UUID as SQLTYPE_UUID , INTEGER, JSONB
import ujson

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# Parse SQL statements from the SQL file
sql_statements = parse_sql_file(Path(__file__).parent / "u2a_user_short_term_memory.sql")

# Extract individual SQL statements
CREATE_TABLE = sql_statements["CreateUserShortTermMemoryTable"]
INSERT_MEMORY = sql_statements["InsertUserShortTermMemory"]
INSERT_MEMORIES_BATCH = sql_statements["InsertUserShortTermMemoriesBatch"]
UPDATE_MEMORY_1 = sql_statements["UpdateUserShortTermMemory1"]
UPDATE_MEMORY_2 = sql_statements["UpdateUserShortTermMemory2"]
UPDATE_MEMORY_3 = sql_statements["UpdateUserShortTermMemory3"]
UPDATE_MEMORY_SESSION_TASK_BY_IDS = sql_statements["UpdateUserShortTermMemorySessionTaskByIds"]
QUERY_MEMORY_BY_ID = sql_statements["QueryUserShortTermMemoryById"]
QUERY_MEMORY_BY_SESSION = sql_statements["QueryUserShortTermMemoryBySession"]
QUERY_MEMORY_BY_SESSION_TASK = sql_statements["QueryUserShortTermMemoryBySessionTask"]
QUERY_MEMORY_BY_USER = sql_statements["QueryUserShortTermMemoryByUser"]
MEMORY_EXISTS = sql_statements["UserShortTermMemoryExists"]
QUERY_MEMORY_FIELD_1 = sql_statements["QueryUserShortTermMemoryField1"]
QUERY_MEMORY_FIELD_2 = sql_statements["QueryUserShortTermMemoryField2"]
QUERY_MEMORY_FIELD_3 = sql_statements["QueryUserShortTermMemoryField3"]
QUERY_MEMORY_FIELD_4 = sql_statements["QueryUserShortTermMemoryField4"]
DELETE_MEMORY = sql_statements["DeleteUserShortTermMemory"]
DELETE_MEMORY_BY_SESSION = sql_statements["DeleteUserShortTermMemoryBySession"]
DELETE_MEMORY_BY_SESSION_TASK = sql_statements["DeleteUserShortTermMemoryBySessionTask"]
GET_NEXT_SEQ_INDEX = sql_statements["GetNextUserShortTermMemorySeqIndex"]

# Data models
@dataclass
class _UserShortTermMemoryCreate:
    user_id: UUID
    session_id: UUID
    content: dict
    seq_index: int | None = None
    session_task_id: UUID | None = None

@dataclass
class _UserShortTermMemoryBatchCreate:
    """批量创建用户短期记忆的数据模型"""
    user_ids: list[UUID]
    session_ids: list[UUID]
    seq_indices: list[int]
    contents: list[dict]
    session_task_ids: list[UUID | None]

@dataclass
class _UserShortTermMemoryUpdate:
    memory_id: UUID
    fields: dict[
        Literal[
            "message_type",
            "content",
            "session_task_id",
        ],
        dict | str | int,
    ]

@dataclass
class _UserShortTermMemoryResponse:
    id: UUID
    user_id: UUID
    session_id: UUID
    seq_index: int
    content: dict
    session_task_id: UUID | None
    created_at: datetime
    updated_at: datetime | None = None

async def create_table() -> None:
    """Create the user short term memory table."""
    async with ASYNC_SQL_ENGINE.begin() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()

# Database operations
async def create_user_short_term_memory(memory_data: _UserShortTermMemoryCreate) -> UUID:
    """Create a new user short term memory record."""
    if memory_data.seq_index is None:
        async with ASYNC_SQL_ENGINE.connect() as conn:
            result = await conn.execute(text(GET_NEXT_SEQ_INDEX), {"session_id": memory_data.session_id})
            memory_data.seq_index = result.scalar()

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(INSERT_MEMORY), {
            "user_id": memory_data.user_id,
            "session_id": memory_data.session_id,
            "seq_index": memory_data.seq_index,
            "content": memory_data.content,
            "session_task_id": memory_data.session_task_id,
        })
        await conn.commit()
        return result.scalar()


async def create_user_short_term_memories_batch(memories_data: _UserShortTermMemoryBatchCreate) -> list[UUID]:
    """批量创建用户短期记忆

    Args:
        memories_data: 批量记忆创建数据

    Returns:
        新记忆的ID列表

    Raises:
        ValueError: 如果输入的列表长度不一致
    """
    # 验证所有列表长度一致
    list_lengths = [
        len(memories_data.user_ids),
        len(memories_data.session_ids),
        len(memories_data.seq_indices),
        len(memories_data.contents),
        len(memories_data.session_task_ids),
    ]

    if len(set(list_lengths)) != 1:
        error_msg = f"All input lists must have the same length. Got lengths: {list_lengths}"
        raise ValueError(error_msg)

    if list_lengths[0] == 0:
        return []

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_MEMORIES_BATCH).bindparams(
                bindparam("user_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("session_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("seq_indices_list", type_=ARRAY(INTEGER)),
                bindparam("contents_list", type_=ARRAY(JSONB)),
                bindparam("session_task_ids_list", type_=ARRAY(SQLTYPE_UUID)),
            ),
            {
                "user_ids_list": memories_data.user_ids,
                "session_ids_list": memories_data.session_ids,
                "seq_indices_list": memories_data.seq_indices,
                "contents_list": memories_data.contents,
                "session_task_ids_list": memories_data.session_task_ids,
            },
        )
        await conn.commit()
        return [row[0] for row in result.fetchall()]


async def create_user_short_term_memories_from_list(memories: list[_UserShortTermMemoryCreate]) -> list[UUID]:
    """从单个记忆列表批量创建用户短期记忆

    Args:
        memories: 单个记忆创建数据列表

    Returns:
        新记忆的ID列表
    """
    if not memories:
        return []

    # 处理seq_index为None的情况
    for memory in memories:
        if memory.seq_index is None:
            async with ASYNC_SQL_ENGINE.connect() as conn:
                result = await conn.execute(text(GET_NEXT_SEQ_INDEX), {"session_id": memory.session_id})
                memory.seq_index = result.scalar()

    batch_data = _UserShortTermMemoryBatchCreate(
        user_ids=[mem.user_id for mem in memories],
        session_ids=[mem.session_id for mem in memories],
        seq_indices=[mem.seq_index for mem in memories],
        contents=[mem.content for mem in memories],
        session_task_ids=[mem.session_task_id for mem in memories]
    )

    return await create_user_short_term_memories_batch(batch_data)

async def get_user_short_term_memory_by_id(
    memory_id: UUID,
) -> _UserShortTermMemoryResponse | None:
    """Get user short term memory by ID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_MEMORY_BY_ID), {"id_value": memory_id})
        row = result.fetchone()

        if row:
            return _UserShortTermMemoryResponse(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
        return None


async def get_user_short_term_memories_by_session(
    session_id: UUID,
) -> list[_UserShortTermMemoryResponse]:
    """Get all user short term memories for a session."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION), {"session_id_value": session_id},
        )
        rows = result.fetchall()

        return [
            _UserShortTermMemoryResponse(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

async def get_user_short_term_memories_by_user(
    user_id: UUID,
) -> list[_UserShortTermMemoryResponse]:
    """Get all user short term memories for a user."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_USER), {"user_id_value": user_id},
        )
        rows = result.fetchall()

        return [
            _UserShortTermMemoryResponse(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

async def update_user_short_term_memory(update_data: _UserShortTermMemoryUpdate) -> bool:
    """Update user short term memory record."""
    field_count = len(update_data.fields)

    if field_count == 0:
        return False
    elif field_count == 1:
        sql = UPDATE_MEMORY_1
    elif field_count == 2:
        sql = UPDATE_MEMORY_2
    elif field_count == 3:
        sql = UPDATE_MEMORY_3
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"id_value": update_data.memory_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0

async def update_memory_session_task_by_ids(
    memory_ids: list[UUID], session_task_id: UUID | None,
) -> int:
    """Update session_task_id for multiple memories by IDs."""
    if not memory_ids:
        return 0

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_MEMORY_SESSION_TASK_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {
                "session_task_id_value": session_task_id,
                "ids_list": memory_ids,
            },
        )
        await conn.commit()
        return result.rowcount

async def delete_user_short_term_memory(memory_id: UUID) -> bool:
    """Delete user short term memory by ID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS), {"id_value": memory_id})
        if result.scalar() == 0:
            return False

        await conn.execute(text(DELETE_MEMORY), {"id_value": memory_id})
        await conn.commit()
        return True


async def delete_user_short_term_memories_by_session(session_id: UUID) -> int:
    """Delete all user short term memories for a session."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_MEMORY_BY_SESSION), {"session_id_value": session_id})
        count = len(result.fetchall())

        if count > 0:
            await conn.execute(text(DELETE_MEMORY_BY_SESSION), {"session_id_value": session_id})
            await conn.commit()

        return count

async def delete_user_short_term_memories_by_session_task(session_task_id: UUID) -> int:
    """Delete all user short term memories for a session and session task."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION_TASK),
            {"session_task_id_value": session_task_id},
        )

        count = len(result.fetchall())
        if count > 0:
            await conn.execute(
                text(DELETE_MEMORY_BY_SESSION_TASK),
                {"session_task_id_value": session_task_id},
            )
            await conn.commit()
        return count

async def memory_exists(memory_id: UUID) -> bool:
    """Check if memory exists by ID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS), {"id_value": memory_id})
        return result.scalar() > 0


async def get_next_seq_index(session_id: UUID) -> int:
    """Get next sequence index for a session."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(GET_NEXT_SEQ_INDEX), {"session_id": session_id})
        return result.scalar()
