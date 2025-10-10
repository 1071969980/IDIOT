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
    Path(__file__).parent / "u2a_agent_short_term_memory.sql"
)

# Extract individual SQL statements
CREATE_TABLE = sql_statements["CreateAgentShortTermMemoryTable"]
INSERT_MEMORY = sql_statements["InsertAgentShortTermMemory"]
UPDATE_MEMORY_1 = sql_statements["UpdateAgentShortTermMemory1"]
UPDATE_MEMORY_2 = sql_statements["UpdateAgentShortTermMemory2"]
UPDATE_MEMORY_3 = sql_statements["UpdateAgentShortTermMemory3"]
UPDATE_MEMORY_SESSION_TASK_BY_IDS = sql_statements["UpdateAgentShortTermMemorySessionTaskByIds"]
QUERY_MEMORY_BY_ID = sql_statements["QueryAgentShortTermMemoryById"]
QUERY_MEMORY_BY_SESSION = sql_statements["QueryAgentShortTermMemoryBySession"]
QUERY_MEMORY_BY_SESSION_TASK = sql_statements["QueryAgentShortTermMemoryBySessionTask"]
QUERY_MEMORY_BY_AGENT = sql_statements["QueryAgentShortTermMemoryByAgent"]
MEMORY_EXISTS = sql_statements["AgentShortTermMemoryExists"]
QUERY_MEMORY_FIELD_1 = sql_statements["QueryAgentShortTermMemoryField1"]
QUERY_MEMORY_FIELD_2 = sql_statements["QueryAgentShortTermMemoryField2"]
QUERY_MEMORY_FIELD_3 = sql_statements["QueryAgentShortTermMemoryField3"]
QUERY_MEMORY_FIELD_4 = sql_statements["QueryAgentShortTermMemoryField4"]
DELETE_MEMORY = sql_statements["DeleteAgentShortTermMemory"]
DELETE_MEMORY_BY_SESSION = sql_statements["DeleteAgentShortTermMemoryBySession"]
GET_NEXT_SUB_SEQ_INDEX = sql_statements["GetNextAgentShortTermMemorySubSeqIndex"]

# Data models
@dataclass
class _AgentShortTermMemoryCreate:
    user_id: UUID
    session_id: UUID
    content: str
    sub_seq_index: int | None = None
    session_task_id: UUID | None = None

@dataclass
class _AgentShortTermMemoryUpdate:
    memory_id: UUID
    fields: dict[
        Literal[
            "message_type",
            "content",
            "session_task_id",
        ],
        str | int,
    ]

@dataclass
class _AgentShortTermMemoryResponse:
    id: UUID
    user_id: UUID
    session_id: UUID
    sub_seq_index: int
    content: str
    session_task_id: UUID | None
    created_at: datetime
    updated_at: datetime | None = None

# Database operations
async def create_agent_short_term_memory(memory_data: _AgentShortTermMemoryCreate) -> UUID:
    """Create a new agent short term memory record."""
    if memory_data.sub_seq_index is None:
        if memory_data.session_task_id is None:
            raise ValueError("session_task_id is required when sub_seq_index is not provided")

        async with ASYNC_SQL_ENGINE.connect() as conn:
            result = await conn.execute(
                text(GET_NEXT_SUB_SEQ_INDEX),
                {
                    "session_id": memory_data.session_id,
                    "session_task_id": memory_data.session_task_id,
                }
            )
            memory_data.sub_seq_index = result.scalar()

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(INSERT_MEMORY), {
            "user_id": memory_data.user_id,
            "session_id": memory_data.session_id,
            "sub_seq_index": memory_data.sub_seq_index,
            "content": memory_data.content,
            "session_task_id": memory_data.session_task_id,
        })
        await conn.commit()
        return result.scalar()

async def get_agent_short_term_memory_by_id(
    memory_id: UUID,
) -> _AgentShortTermMemoryResponse | None:
    """Get agent short term memory by ID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_MEMORY_BY_ID), {"id_value": memory_id})
        row = result.fetchone()

        if row:
            return _AgentShortTermMemoryResponse(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
        return None


async def get_agent_short_term_memories_by_session(
    session_id: UUID,
) -> list[_AgentShortTermMemoryResponse]:
    """Get all agent short term memories for a session."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION), {"session_id_value": session_id}
        )
        rows = result.fetchall()

        return [
            _AgentShortTermMemoryResponse(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

async def get_agent_short_term_memories_by_session_task(
    session_id: UUID, session_task_id: UUID,
) -> list[_AgentShortTermMemoryResponse]:
    """Get all agent short term memories for a specific session task."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION_TASK),
            {
                "session_id_value": session_id,
                "session_task_id_value": session_task_id,
            }
        )
        rows = result.fetchall()

        return [
            _AgentShortTermMemoryResponse(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

async def get_agent_short_term_memories_by_agent(
    user_id: UUID,
) -> list[_AgentShortTermMemoryResponse]:
    """Get all agent short term memories for an agent."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_AGENT), {"user_id_value": user_id}
        )
        rows = result.fetchall()

        return [
            _AgentShortTermMemoryResponse(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                content=row.content,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

async def update_agent_short_term_memory(update_data: _AgentShortTermMemoryUpdate) -> bool:
    """Update agent short term memory record."""
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
        error_msg = f"Unsupported field count: {field_count}"
        raise ValueError(error_msg)

    params = {"id_value": update_data.memory_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0

async def update_memory_session_task_by_ids(
    memory_ids: list[UUID], session_task_id: UUID | None
) -> int:
    """Update session_task_id for multiple memories by IDs."""
    if not memory_ids:
        return 0

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_MEMORY_SESSION_TASK_BY_IDS),
            {
                "session_task_id_value": session_task_id,
                "ids_list": tuple(memory_ids),
            },
        )
        await conn.commit()
        return result.rowcount

async def delete_agent_short_term_memory(memory_id: UUID) -> bool:
    """Delete agent short term memory by ID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS), {"id_value": memory_id})
        if result.scalar() == 0:
            return False

        await conn.execute(text(DELETE_MEMORY), {"id_value": memory_id})
        await conn.commit()
        return True


async def delete_agent_short_term_memories_by_session(session_id: UUID) -> int:
    """Delete all agent short term memories for a session."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION), {"session_id_value": session_id}
        )
        count = len(result.fetchall())

        if count > 0:
            await conn.execute(
                text(DELETE_MEMORY_BY_SESSION), {"session_id_value": session_id}
            )
            await conn.commit()

        return count

async def memory_exists(memory_id: UUID) -> bool:
    """Check if memory exists by ID."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(MEMORY_EXISTS), {"id_value": memory_id})
        return result.scalar() > 0


async def get_next_sub_seq_index(session_id: UUID, session_task_id: UUID) -> int:
    """Get next sub-sequence index for a session task."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_NEXT_SUB_SEQ_INDEX),
            {"session_id": session_id, "session_task_id": session_task_id},
        )
        return result.scalar()
