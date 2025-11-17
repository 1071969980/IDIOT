from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, List, Literal, Union
from uuid import UUID

from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import ARRAY, UUID as SQLTYPE_UUID , INTEGER, JSONB, TEXT

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file
import ujson

# Parse SQL statements from the SQL file
sql_statements = parse_sql_file(
    Path(__file__).parent / "u2a_agent_short_term_memory.sql"
)

# Extract individual SQL statements
CREATE_TABLE = sql_statements["CreateAgentShortTermMemoryTable"]
INSERT_MEMORY = sql_statements["InsertAgentShortTermMemory"]
INSERT_MEMORIES_BATCH = sql_statements["InsertAgentShortTermMemoriesBatch"]
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
DELETE_MEMORY_BY_SESSION_TASK = sql_statements["DeleteAgentShortTermMemoryBySessionTask"]
GET_NEXT_SUB_SEQ_INDEX = sql_statements["GetNextAgentShortTermMemorySubSeqIndex"]


# Data models
@dataclass
class _AgentShortTermMemoryCreate:
    user_id: UUID
    session_id: UUID
    content: dict
    sub_seq_index: int
    session_task_id: UUID | None = None


@dataclass
class _AgentShortTermMemoryBatchCreate:
    """批量创建代理短期记忆的数据模型"""
    user_ids: list[UUID]
    session_ids: list[UUID]
    sub_seq_indices: list[int]
    contents: list[dict]
    session_task_ids: list[UUID | None]

@dataclass
class _AgentShortTermMemoryUpdate:
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
class _AgentShortTermMemoryResponse:
    id: UUID
    user_id: UUID
    session_id: UUID
    sub_seq_index: int
    content: dict
    session_task_id: UUID | None
    created_at: datetime
    updated_at: datetime | None = None

async def create_table() -> None:
    """Create the agent short term memory table if it does not exist."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()

# Database operations
async def create_agent_short_term_memory(memory_data: _AgentShortTermMemoryCreate) -> UUID:
    """Create a new agent short term memory record."""
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


async def create_agent_short_term_memory_with_auto_index(
    user_id: UUID,
    session_id: UUID,
    content: dict,
    session_task_id: UUID
) -> UUID:
    """创建代理短期记忆并自动分配sub_seq_index

    Args:
        user_id: 用户ID
        session_id: 会话ID
        content: 记忆内容
        session_task_id: 会话任务ID

    Returns:
        新记忆的ID
    """
    # 获取下一个sub_seq_index
    sub_seq_index = await get_next_sub_seq_index(session_id, session_task_id)

    memory_data = _AgentShortTermMemoryCreate(
        user_id=user_id,
        session_id=session_id,
        content=content,
        sub_seq_index=sub_seq_index,
        session_task_id=session_task_id
    )

    return await create_agent_short_term_memory(memory_data)


async def create_agent_short_term_memories_batch(memories_data: _AgentShortTermMemoryBatchCreate) -> list[UUID]:
    """批量创建代理短期记忆

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
        len(memories_data.sub_seq_indices),
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
                bindparam("sub_seq_indices_list", type_=ARRAY(INTEGER)),
                bindparam("contents_list", type_=ARRAY(JSONB)),
                bindparam("session_task_ids_list", type_=ARRAY(SQLTYPE_UUID)),
            ),
            {
                "user_ids_list": memories_data.user_ids,
                "session_ids_list": memories_data.session_ids,
                "sub_seq_indices_list": memories_data.sub_seq_indices,
                "contents_list": [ujson.dumps(content, ensure_ascii=False) for content in memories_data.contents],
                "session_task_ids_list": memories_data.session_task_ids,
            },
        )
        await conn.commit()
        return [row[0] for row in result.fetchall()]


async def create_agent_short_term_memories_from_list(memories: list[_AgentShortTermMemoryCreate]) -> list[UUID]:
    """从单个记忆列表批量创建代理短期记忆

    Args:
        memories: 单个记忆创建数据列表

    Returns:
        新记忆的ID列表
    """
    if not memories:
        return []

    batch_data = _AgentShortTermMemoryBatchCreate(
        user_ids=[mem.user_id for mem in memories],
        session_ids=[mem.session_id for mem in memories],
        sub_seq_indices=[mem.sub_seq_index for mem in memories],
        contents=[mem.content for mem in memories],
        session_task_ids=[mem.session_task_id for mem in memories]
    )

    return await create_agent_short_term_memories_batch(batch_data)

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
    session_task_id: UUID,
) -> list[_AgentShortTermMemoryResponse]:
    """Get all agent short term memories for a specific session task."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION_TASK),
            {
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
    
async def delete_agent_short_term_memories_by_session_task(
    session_task_id: UUID,
) -> int:
    """Delete all agent short term memories for a session task."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_MEMORY_BY_SESSION_TASK),
            {"session_task_id_value": session_task_id}
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


async def get_next_sub_seq_index(session_id: UUID, session_task_id: UUID) -> int:
    """Get next sub-sequence index for a session task."""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_NEXT_SUB_SEQ_INDEX),
            {"session_id": session_id, "session_task_id": session_task_id},
        )
        return result.scalar()
