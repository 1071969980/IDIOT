from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy import text

from api.sql_orm_models import ASYNC_SQL_ENGINE
from api.sql_orm_models.utils import parse_sql_file

# Parse SQL statements from the SQL file
sql_statements = parse_sql_file(
    Path(__file__).parent / "a2a_session_short_term_memory.sql"
)

# Extract individual SQL statements
CREATE_TABLE = sql_statements["CreateTable"]
INSERT_MEMORY = sql_statements["InsertMemory"]
INSERT_MEMORIES_BATCH = sql_statements["InsertMemoriesBatch"]
UPDATE_MEMORY_1 = sql_statements["UpdateMemory1"]
UPDATE_MEMORY_2 = sql_statements["UpdateMemory2"]
UPDATE_MEMORY_3 = sql_statements["UpdateMemory3"]
UPDATE_MEMORY_SESSION_TASK_BY_IDS = sql_statements["UpdateMemorySessionTaskByIds"]
QUERY_MEMORY_BY_ID = sql_statements["QueryMemoryById"]
QUERY_MEMORY_BY_SESSION = sql_statements["QueryMemoryBySession"]
QUERY_MEMORY_BY_SESSION_TASK = sql_statements["QueryMemoryBySessionTask"]
QUERY_MEMORY_BY_SESSION_AND_TASK = sql_statements["QueryMemoryBySessionAndTask"]
MEMORY_EXISTS = sql_statements["MemoryExists"]
QUERY_MEMORY_FIELD_1 = sql_statements["QueryMemoryField1"]
QUERY_MEMORY_FIELD_2 = sql_statements["QueryMemoryField2"]
QUERY_MEMORY_FIELD_3 = sql_statements["QueryMemoryField3"]
QUERY_MEMORY_FIELD_4 = sql_statements["QueryMemoryField4"]
DELETE_MEMORY = sql_statements["DeleteMemory"]
DELETE_MEMORY_BY_SESSION = sql_statements["DeleteMemoryBySession"]
DELETE_MEMORY_BY_SESSION_TASK = sql_statements["DeleteMemoryBySessionTask"]
DELETE_MEMORY_BY_SESSION_AND_TASK = sql_statements["DeleteMemoryBySessionAndTask"]
GET_NEXT_SEQ_INDEX = sql_statements["GetNextSeqIndex"]

# Table name constants
A_SIDE_TABLE = "a2a_A_side_agent_short_term_memory"
B_SIDE_TABLE = "a2a_B_side_agent_short_term_memory"

# Data models
@dataclass
class _SessionShortTermMemoryCreate:
    """会话短期记忆创建数据模型"""
    session_id: UUID
    session_task_id: UUID
    content: dict
    seq_index: int

@dataclass
class _SessionShortTermMemoryBatchCreate:
    """批量创建会话短期记忆的数据模型"""
    session_ids: list[UUID]
    session_task_ids: list[UUID]
    seq_indices: list[int]
    contents: list[dict]

@dataclass
class _SessionShortTermMemoryUpdate:
    """会话短期记忆更新数据模型"""
    memory_id: UUID
    fields: dict[
        Literal[
            "session_id",
            "session_task_id",
            "seq_index",
            "content",
        ],
        dict | str | int | UUID,
    ]

@dataclass
class _SessionShortTermMemoryResponse:
    """会话短期记忆响应数据模型"""
    id: UUID
    session_id: UUID
    session_task_id: UUID
    seq_index: int
    content: dict
    created_at: datetime


async def create_tables() -> None:
    """Create the session short term memory tables if they do not exist."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stat in CREATE_TABLE:
            await conn.execute(text(stat))
        await conn.commit()


async def create_session_short_term_memory(
    memory_data: _SessionShortTermMemoryCreate,
    table_side: Literal["A", "B"]
) -> UUID:
    """Create a new session short term memory record.

    Args:
        memory_data: Memory creation data
        table_side: Which side table to use ("A" or "B")

    Returns:
        The UUID of the new memory record
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(INSERT_MEMORY), {
            "table_name": table_name,
            "session_id": memory_data.session_id,
            "session_task_id": memory_data.session_task_id,
            "seq_index": memory_data.seq_index,
            "content": memory_data.content,
        })
        await conn.commit()
        return result.scalar()


async def create_session_short_term_memory_with_auto_index(
    session_id: UUID,
    session_task_id: UUID,
    content: dict,
    table_side: Literal["A", "B"]
) -> UUID:
    """Create session short term memory with auto-generated seq_index.

    Args:
        session_id: Session UUID
        session_task_id: Session task UUID
        content: Memory content (dict)
        table_side: Which side table to use ("A" or "B")

    Returns:
        The UUID of the new memory record
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    # Get next seq_index
    seq_index = await get_next_seq_index(session_id, session_task_id, table_name)

    memory_data = _SessionShortTermMemoryCreate(
        session_id=session_id,
        session_task_id=session_task_id,
        content=content,
        seq_index=seq_index
    )

    return await create_session_short_term_memory(memory_data, table_side)


async def create_session_short_term_memories_batch(
    memories_data: _SessionShortTermMemoryBatchCreate,
    table_side: Literal["A", "B"]
) -> list[UUID]:
    """Batch create session short term memories.

    Args:
        memories_data: Batch memory creation data
        table_side: Which side table to use ("A" or "B")

    Returns:
        List of new memory UUIDs

    Raises:
        ValueError: If input lists have inconsistent lengths
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    # Validate all lists have same length
    list_lengths = [
        len(memories_data.session_ids),
        len(memories_data.session_task_ids),
        len(memories_data.seq_indices),
        len(memories_data.contents)
    ]

    if len(set(list_lengths)) != 1:
        raise ValueError(f"All input lists must have the same length. Got lengths: {list_lengths}")

    if list_lengths[0] == 0:
        return []

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_MEMORIES_BATCH),
            {
                "table_name": table_name,
                "session_ids_list": tuple(memories_data.session_ids),
                "session_task_ids_list": tuple(memories_data.session_task_ids),
                "seq_indices_list": tuple(memories_data.seq_indices),
                "contents_list": tuple(memories_data.contents)
            }
        )
        await conn.commit()
        return [row[0] for row in result.fetchall()]


async def get_session_short_term_memory_by_id(
    memory_id: UUID,
    table_side: Literal["A", "B"]
) -> _SessionShortTermMemoryResponse | None:
    """Get session short term memory by ID.

    Args:
        memory_id: Memory UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        Memory response or None if not found
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_MEMORY_BY_ID), {
            "table_name": table_name,
            "id_value": memory_id
        })
        row = result.fetchone()

        if row:
            return _SessionShortTermMemoryResponse(
                id=row.id,
                session_id=row.session_id,
                session_task_id=row.session_task_id,
                seq_index=row.seq_index,
                content=row.content,
                created_at=row.created_at,
            )
        return None


async def get_session_short_term_memories_by_session(
    session_id: UUID,
    table_side: Literal["A", "B"]
) -> list[_SessionShortTermMemoryResponse]:
    """Get all session short term memories for a session.

    Args:
        session_id: Session UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        List of memory responses ordered by seq_index
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION), {
                "table_name": table_name,
                "session_id_value": session_id
            }
        )
        rows = result.fetchall()

        return [
            _SessionShortTermMemoryResponse(
                id=row.id,
                session_id=row.session_id,
                session_task_id=row.session_task_id,
                seq_index=row.seq_index,
                content=row.content,
                created_at=row.created_at,
            )
            for row in rows
        ]


async def get_session_short_term_memories_by_session_task(
    session_task_id: UUID,
    table_side: Literal["A", "B"]
) -> list[_SessionShortTermMemoryResponse]:
    """Get all session short term memories for a specific session task.

    Args:
        session_task_id: Session task UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        List of memory responses ordered by seq_index
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION_TASK),
            {
                "table_name": table_name,
                "session_task_id_value": session_task_id,
            }
        )
        rows = result.fetchall()

        return [
            _SessionShortTermMemoryResponse(
                id=row.id,
                session_id=row.session_id,
                session_task_id=row.session_task_id,
                seq_index=row.seq_index,
                content=row.content,
                created_at=row.created_at,
            )
            for row in rows
        ]


async def get_session_short_term_memories_by_session_and_task(
    session_id: UUID,
    session_task_id: UUID,
    table_side: Literal["A", "B"]
) -> list[_SessionShortTermMemoryResponse]:
    """Get session short term memories for a specific session and task.

    Args:
        session_id: Session UUID
        session_task_id: Session task UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        List of memory responses ordered by seq_index
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION_AND_TASK),
            {
                "table_name": table_name,
                "session_id_value": session_id,
                "session_task_id_value": session_task_id,
            }
        )
        rows = result.fetchall()

        return [
            _SessionShortTermMemoryResponse(
                id=row.id,
                session_id=row.session_id,
                session_task_id=row.session_task_id,
                seq_index=row.seq_index,
                content=row.content,
                created_at=row.created_at,
            )
            for row in rows
        ]


async def update_session_short_term_memory(
    update_data: _SessionShortTermMemoryUpdate,
    table_side: Literal["A", "B"]
) -> bool:
    """Update session short term memory record.

    Args:
        update_data: Memory update data
        table_side: Which side table to use ("A" or "B")

    Returns:
        True if record was updated, False otherwise

    Raises:
        ValueError: If unsupported number of fields
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE
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

    params = {"table_name": table_name, "id_value": update_data.memory_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0


async def delete_session_short_term_memory(
    memory_id: UUID,
    table_side: Literal["A", "B"]
) -> bool:
    """Delete session short term memory by ID.

    Args:
        memory_id: Memory UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        True if memory was deleted, False if it didn't exist
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS), {
            "table_name": table_name,
            "id_value": memory_id
        })
        if result.scalar() == 0:
            return False

        await conn.execute(text(DELETE_MEMORY), {
            "table_name": table_name,
            "id_value": memory_id
        })
        await conn.commit()
        return True


async def delete_session_short_term_memories_by_session(
    session_id: UUID,
    table_side: Literal["A", "B"]
) -> int:
    """Delete all session short term memories for a session.

    Args:
        session_id: Session UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        Number of memories deleted
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION), {
                "table_name": table_name,
                "session_id_value": session_id
            }
        )
        count = len(result.fetchall())

        if count > 0:
            await conn.execute(
                text(DELETE_MEMORY_BY_SESSION), {
                    "table_name": table_name,
                    "session_id_value": session_id
                }
            )
            await conn.commit()

        return count


async def delete_session_short_term_memories_by_session_task(
    session_task_id: UUID,
    table_side: Literal["A", "B"]
) -> int:
    """Delete all session short term memories for a session task.

    Args:
        session_task_id: Session task UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        Number of memories deleted
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION_TASK),
            {
                "table_name": table_name,
                "session_task_id_value": session_task_id
            }
        )
        count = len(result.fetchall())

        if count > 0:
            await conn.execute(
                text(DELETE_MEMORY_BY_SESSION_TASK),
                {
                    "table_name": table_name,
                    "session_task_id_value": session_task_id,
                }
            )
            await conn.commit()

        return count


async def delete_session_short_term_memories_by_session_and_task(
    session_id: UUID,
    session_task_id: UUID,
    table_side: Literal["A", "B"]
) -> int:
    """Delete session short term memories for a specific session and task.

    Args:
        session_id: Session UUID
        session_task_id: Session task UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        Number of memories deleted
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION_AND_TASK),
            {
                "table_name": table_name,
                "session_id_value": session_id,
                "session_task_id_value": session_task_id,
            }
        )
        count = len(result.fetchall())

        if count > 0:
            await conn.execute(
                text(DELETE_MEMORY_BY_SESSION_AND_TASK),
                {
                    "table_name": table_name,
                    "session_id_value": session_id,
                    "session_task_id_value": session_task_id,
                }
            )
            await conn.commit()

        return count


async def memory_exists(
    memory_id: UUID,
    table_side: Literal["A", "B"]
) -> bool:
    """Check if memory exists by ID.

    Args:
        memory_id: Memory UUID
        table_side: Which side table to use ("A" or "B")

    Returns:
        True if memory exists, False otherwise
    """
    table_name = A_SIDE_TABLE if table_side == "A" else B_SIDE_TABLE

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS), {
            "table_name": table_name,
            "id_value": memory_id
        })
        return result.scalar() > 0


async def get_next_seq_index(
    session_id: UUID,
    session_task_id: UUID,
    table_name: str
) -> int:
    """Get next sequence index for a session task.

    Args:
        session_id: Session UUID
        session_task_id: Session task UUID
        table_name: The table name to query

    Returns:
        Next available sequence index
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_NEXT_SEQ_INDEX),
            {
                "table_name": table_name,
                "session_id": session_id,
                "session_task_id": session_task_id,
            },
        )
        return result.scalar()