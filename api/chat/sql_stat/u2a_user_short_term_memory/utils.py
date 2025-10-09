from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlalchemy import text

from api.sql_orm_models import ASYNC_SQL_ENGINE
from api.sql_orm_models.utils import parse_sql_file

# Parse SQL statements from the SQL file
sql_statements = parse_sql_file(Path(__file__).parent / "u2a_user_short_term_memory.sql")

# Extract individual SQL statements
CREATE_TABLE = sql_statements["CreateUserShortTermMemoryTable"]
INSERT_MEMORY = sql_statements["InsertUserShortTermMemory"]
UPDATE_MEMORY_1 = sql_statements["UpdateUserShortTermMemory1"]
UPDATE_MEMORY_2 = sql_statements["UpdateUserShortTermMemory2"]
UPDATE_MEMORY_3 = sql_statements["UpdateUserShortTermMemory3"]
UPDATE_MEMORY_SESSION_TASK_BY_UUIDS = sql_statements["UpdateUserShortTermMemorySessionTaskByUuids"]
QUERY_MEMORY_BY_ID = sql_statements["QueryUserShortTermMemoryById"]
QUERY_MEMORY_BY_UUID = sql_statements["QueryUserShortTermMemoryByUuid"]
QUERY_MEMORY_BY_SESSION = sql_statements["QueryUserShortTermMemoryBySession"]
QUERY_MEMORY_BY_USER = sql_statements["QueryUserShortTermMemoryByUser"]
MEMORY_EXISTS = sql_statements["UserShortTermMemoryExists"]
MEMORY_EXISTS_BY_UUID = sql_statements["UserShortTermMemoryExistsByUuid"]
QUERY_MEMORY_FIELD_1 = sql_statements["QueryUserShortTermMemoryField1"]
QUERY_MEMORY_FIELD_2 = sql_statements["QueryUserShortTermMemoryField2"]
QUERY_MEMORY_FIELD_3 = sql_statements["QueryUserShortTermMemoryField3"]
QUERY_MEMORY_FIELD_4 = sql_statements["QueryUserShortTermMemoryField4"]
DELETE_MEMORY = sql_statements["DeleteUserShortTermMemory"]
DELETE_MEMORY_BY_UUID = sql_statements["DeleteUserShortTermMemoryByUuid"]
DELETE_MEMORY_BY_SESSION = sql_statements["DeleteUserShortTermMemoryBySession"]
GET_NEXT_SEQ_INDEX = sql_statements["GetNextUserShortTermMemorySeqIndex"]

# Data models
@dataclass
class _UserShortTermMemoryCreate:
    user_id: str
    session_id: str
    message_type: str
    content: str
    seq_index: int | None = None
    message_uuid: str | None = None
    session_task_id: str | None = None

@dataclass
class _UserShortTermMemoryUpdate:
    memory_id: int
    fields: dict[
        Literal[
            "message_type",
            "content",
            "session_task_id",
        ],
        str | int,
    ]

@dataclass
class _UserShortTermMemoryResponse:
    id: int
    user_id: str
    session_id: str
    seq_index: int
    message_uuid: str
    message_type: str
    content: str
    session_task_id: str | None
    created_at: datetime
    updated_at: datetime | None = None

# Database operations
async def create_user_short_term_memory(memory_data: _UserShortTermMemoryCreate) -> str:
    """Create a new user short term memory record."""
    if not memory_data.message_uuid:
        memory_data.message_uuid = str(uuid4())

    if memory_data.seq_index is None:
        async with ASYNC_SQL_ENGINE.connect() as conn:
            result = await conn.execute(text(GET_NEXT_SEQ_INDEX), {"session_id": memory_data.session_id})
            memory_data.seq_index = result.scalar()

    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(INSERT_MEMORY), {
            "user_id": memory_data.user_id,
            "session_id": memory_data.session_id,
            "seq_index": memory_data.seq_index,
            "message_uuid": memory_data.message_uuid,
            "message_type": memory_data.message_type,
            "content": memory_data.content,
            "session_task_id": memory_data.session_task_id,
        })
        await conn.commit()
        return memory_data.message_uuid

async def get_user_short_term_memory_by_id(
    memory_id: int,
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
                message_uuid=row.message_uuid,
                message_type=row.message_type,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
        return None

async def get_user_short_term_memory_by_uuid(
    memory_uuid: str,
) -> _UserShortTermMemoryResponse | None:
    """Get user short term memory by UUID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_UUID), {"memory_uuid_value": memory_uuid},
        )
        row = result.fetchone()

        if row:
            return _UserShortTermMemoryResponse(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_uuid=row.message_uuid,
                message_type=row.message_type,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
        return None

async def get_user_short_term_memories_by_session(
    session_id: str,
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
                message_uuid=row.message_uuid,
                message_type=row.message_type,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

async def get_user_short_term_memories_by_user(
    user_id: str,
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
                message_uuid=row.message_uuid,
                message_type=row.message_type,
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

async def update_memory_session_task_by_uuids(memory_uuids: list[str], session_task_id: str | None) -> int:
    """Update session_task_id for multiple memories by UUIDs."""
    if not memory_uuids:
        return 0

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_MEMORY_SESSION_TASK_BY_UUIDS),
            {
                "session_task_id_value": session_task_id,
                "uuids_list": tuple(memory_uuids),
            },
        )
        await conn.commit()
        return result.rowcount

async def delete_user_short_term_memory(memory_id: int) -> bool:
    """Delete user short term memory by ID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS), {"id_value": memory_id})
        if result.scalar() == 0:
            return False

        await conn.execute(text(DELETE_MEMORY), {"id_value": memory_id})
        await conn.commit()
        return True

async def delete_user_short_term_memory_by_uuid(memory_uuid: str) -> bool:
    """Delete user short term memory by UUID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS_BY_UUID), {"memory_uuid_value": memory_uuid})
        if result.scalar() == 0:
            return False

        await conn.execute(text(DELETE_MEMORY_BY_UUID), {"memory_uuid_value": memory_uuid})
        await conn.commit()
        return True

async def delete_user_short_term_memories_by_session(session_id: str) -> int:
    """Delete all user short term memories for a session."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_MEMORY_BY_SESSION), {"session_id_value": session_id})
        count = len(result.fetchall())

        if count > 0:
            await conn.execute(text(DELETE_MEMORY_BY_SESSION), {"session_id_value": session_id})
            await conn.commit()

        return count

async def memory_exists(memory_id: int) -> bool:
    """Check if memory exists by ID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS), {"id_value": memory_id})
        return result.scalar() > 0

async def memory_exists_by_uuid(memory_uuid: str) -> bool:
    """Check if memory exists by UUID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS_BY_UUID), {"memory_uuid_value": memory_uuid})
        return result.scalar() > 0

async def get_next_seq_index(session_id: str) -> int:
    """Get next sequence index for a session."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(GET_NEXT_SEQ_INDEX), {"session_id": session_id})
        return result.scalar()
