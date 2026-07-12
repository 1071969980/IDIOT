from dataclasses import dataclass
from typing import Optional, Dict, Any, Literal
from uuid import UUID
from datetime import datetime
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import ARRAY, UUID as SQLTYPE_UUID , INTEGER, JSONB, TEXT, VARCHAR

from api.sql_utils.utils import SQL_OP_ContextData, _resolve_conn, parse_sql_file
from pathlib import Path

sql_file_path = Path(__file__).parent / "U2AAgentMsg.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_AGENT_MESSAGES_TABLE = sql_statements.get_list("CreateAgentMessagesTable")
CREATE_AGENT_MESSAGE_TRIGGERS = sql_statements.get_list("CreateAgentMessageTriggers")

INSERT_AGENT_MESSAGE = sql_statements.get_str("InsertAgentMessage")
INSERT_AGENT_MESSAGES_BATCH = sql_statements.get_str("InsertAgentMessagesBatch")

UPDATE_AGENT_MESSAGE_STATUS_BY_IDS = sql_statements.get_str("UpdateAgentMessageStatusByIds")
UPDATE_AGENT_MESSAGE_SESSION_TASK_BY_IDS = sql_statements.get_str("UpdateAgentMessageSessionTaskByIds")

CHECK_AGENT_MESSAGE_EXISTS = sql_statements.get_str("AgentMessageExists")
QUERY_AGENT_MESSAGE_BY_ID = sql_statements.get_str("QueryAgentMessageById")
QUERY_AGENT_MESSAGES_BY_SESSION = sql_statements.get_str("QueryAgentMessagesBySession")
QUERY_AGENT_MESSAGES_BY_SESSION_TASK = sql_statements.get_str("QueryAgentMessagesBySessionTask")
QUERY_AGENT_MESSAGES_BY_USER = sql_statements.get_str("QueryAgentMessagesByUser")
DELETE_AGENT_MESSAGE = sql_statements.get_str("DeleteAgentMessage")
DELETE_AGENT_MESSAGES_BY_SESSION = sql_statements.get_str("DeleteAgentMessagesBySession")
DELETE_AGENT_MESSAGES_BY_SESSION_TASK = sql_statements.get_str("DeleteAgentMessagesBySessionTask")
GET_NEXT_AGENT_MESSAGE_SUB_SEQ_INDEX = sql_statements.get_str("GetNextAgentMessageSubSeqIndex")
QUERY_AGENT_MESSAGES_BY_SESSION_TASK_IDS = sql_statements.get_str("QueryAgentMessagesBySessionTaskIds")


@dataclass
class _U2AAgentMessage:
    """U2A代理消息数据模型"""
    id: UUID
    user_id: UUID
    session_id: UUID
    sub_seq_index: int
    message_type: str
    content: str
    status: str
    session_task_id: UUID
    present_priority: int
    created_at: datetime
    updated_at: datetime
    json_content: Optional[Dict[str, Any]] = None


@dataclass
class _U2AAgentMessageCreate:
    """创建U2A代理消息的数据模型"""
    user_id: UUID
    session_id: UUID
    session_task_id: UUID
    sub_seq_index: int
    message_type: str
    content: str
    status: str
    json_content: Optional[Dict[str, Any]] = None
    present_priority: int = 30


@dataclass
class _U2AAgentMessageBatchCreate:
    """批量创建U2A代理消息的数据模型"""
    user_ids: list[UUID]
    session_ids: list[UUID]
    sub_seq_indices: list[int]
    message_types: list[str]
    contents: list[str]
    json_contents: list[Optional[Dict[str, Any]]]
    statuses: list[str]
    session_task_ids: list[Optional[UUID]]
    present_priorities: list[int]


async def create_table(ctx: SQL_OP_ContextData | None = None) -> None:
    """创建U2A代理消息表并设置触发器"""
    async with _resolve_conn(ctx) as conn:
        for stmt in CREATE_AGENT_MESSAGES_TABLE:
            await conn.execute(text(stmt))
        for stmt in CREATE_AGENT_MESSAGE_TRIGGERS:
            await conn.execute(text(stmt))
        if ctx is None or ctx.auto_commit:
            await conn.commit()


async def insert_agent_message(
    message_data: _U2AAgentMessageCreate,
    ctx: SQL_OP_ContextData | None = None,
) -> UUID:
    """插入新U2A代理消息

    Args:
        message_data: 消息创建数据
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        新消息的ID
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(INSERT_AGENT_MESSAGE).bindparams(
                bindparam("user_id", type_=SQLTYPE_UUID),
                bindparam("session_id", type_=SQLTYPE_UUID),
                bindparam("session_task_id", type_=SQLTYPE_UUID),
                bindparam("json_content", type_=JSONB),
            ),
            {
                "user_id": message_data.user_id,
                "session_id": message_data.session_id,
                "session_task_id": message_data.session_task_id,
                "sub_seq_index": message_data.sub_seq_index,
                "message_type": message_data.message_type,
                "content": message_data.content,
                "json_content": message_data.json_content,
                "status": message_data.status,
                "present_priority": message_data.present_priority,
            }
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.scalar()


async def insert_agent_messages_batch(
    messages_data: _U2AAgentMessageBatchCreate,
    ctx: SQL_OP_ContextData | None = None,
) -> list[UUID]:
    """批量插入U2A代理消息

    Args:
        messages_data: 批量消息创建数据
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        新消息的ID列表

    Raises:
        ValueError: 如果输入的列表长度不一致
    """
    # 验证所有列表长度一致
    list_lengths = [
        len(messages_data.user_ids),
        len(messages_data.session_ids),
        len(messages_data.sub_seq_indices),
        len(messages_data.message_types),
        len(messages_data.contents),
        len(messages_data.json_contents),
        len(messages_data.statuses),
        len(messages_data.session_task_ids),
        len(messages_data.present_priorities),
    ]

    if len(set(list_lengths)) != 1:
        error_msg = f"All input lists must have the same length. Got lengths: {list_lengths}"
        raise ValueError(error_msg)

    if list_lengths[0] == 0:
        return []

    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(INSERT_AGENT_MESSAGES_BATCH).bindparams(
                bindparam("user_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("session_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("sub_seq_indices_list", type_=ARRAY(INTEGER)),
                bindparam("message_types_list", type_=ARRAY(VARCHAR)),
                bindparam("contents_list", type_=ARRAY(TEXT)),
                bindparam("json_contents_list", type_=ARRAY(JSONB)),
                bindparam("statuses_list", type_=ARRAY(VARCHAR)),
                bindparam("session_task_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("present_priorities_list", type_=ARRAY(INTEGER)),
            ),
            {
                "user_ids_list": messages_data.user_ids,
                "session_ids_list": messages_data.session_ids,
                "sub_seq_indices_list": messages_data.sub_seq_indices,
                "message_types_list": messages_data.message_types,
                "contents_list": messages_data.contents,
                "json_contents_list": messages_data.json_contents,
                "statuses_list": messages_data.statuses,
                "session_task_ids_list": messages_data.session_task_ids,
                "present_priorities_list": messages_data.present_priorities,
            },
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return [row[0] for row in result.fetchall()]


async def insert_agent_messages_from_list(
    messages: list[_U2AAgentMessageCreate],
    ctx: SQL_OP_ContextData | None = None,
) -> list[UUID]:
    """从单个消息列表批量插入U2A代理消息

    Args:
        messages: 单个消息创建数据列表
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        新消息的ID列表
    """
    if not messages:
        return []

    batch_data = _U2AAgentMessageBatchCreate(
        user_ids=[msg.user_id for msg in messages],
        session_ids=[msg.session_id for msg in messages],
        session_task_ids=[msg.session_task_id for msg in messages],
        sub_seq_indices=[msg.sub_seq_index for msg in messages],
        message_types=[msg.message_type for msg in messages],
        contents=[msg.content for msg in messages],
        json_contents=[msg.json_content for msg in messages],
        statuses=[msg.status for msg in messages],
        present_priorities=[msg.present_priority for msg in messages],
    )

    return await insert_agent_messages_batch(batch_data, ctx=ctx)


async def get_next_agent_message_sub_seq_index(
    session_task_id: Optional[UUID],
    ctx: SQL_OP_ContextData | None = None,
) -> int:
    """获取会话的下一条代理消息子序列索引

    Args:
        session_task_id: 会话任务ID（可选）
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        下一条代理消息的子序列索引
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(GET_NEXT_AGENT_MESSAGE_SUB_SEQ_INDEX),
            {"session_task_id": session_task_id}
        )
        return result.scalar()


async def check_agent_message_exists(
    message_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """检查代理消息是否存在

    Args:
        message_id: 消息ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        消息是否存在
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(CHECK_AGENT_MESSAGE_EXISTS), {"id_value": message_id})
        count = result.scalar()
        return count > 0


async def get_agent_message_by_id(
    message_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> Optional[_U2AAgentMessage]:
    """获取代理消息信息

    Args:
        message_id: 消息ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        消息信息，如果不存在则返回None
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(QUERY_AGENT_MESSAGE_BY_ID), {"id_value": message_id})
        row = result.first()

        if row is None:
            return None

        return _U2AAgentMessage(
            id=row.id,
            user_id=row.user_id,
            session_id=row.session_id,
            sub_seq_index=row.sub_seq_index,
            message_type=row.message_type,
            content=row.content,
            json_content=row.json_content,
            status=row.status,
            session_task_id=row.session_task_id,
            present_priority=row.present_priority,
            created_at=row.created_at,
            updated_at=row.updated_at
        )


async def get_agent_messages_by_session(
    session_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> list[_U2AAgentMessage]:
    """根据会话ID获取所有代理消息

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        代理消息列表
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(QUERY_AGENT_MESSAGES_BY_SESSION), {"session_id_value": session_id})
        rows = result.fetchall()

        messages = []
        for row in rows:
            messages.append(_U2AAgentMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                message_type=row.message_type,
                content=row.content,
                json_content=row.json_content,
                status=row.status,
                session_task_id=row.session_task_id,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return messages


async def get_agent_messages_by_session_task(
    session_task_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> list[_U2AAgentMessage]:
    """根据会话任务ID获取代理消息

    Args:
        session_task_id: 会话任务ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        代理消息列表
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(QUERY_AGENT_MESSAGES_BY_SESSION_TASK),
            {
                "session_task_id_value": session_task_id
            }
        )
        rows = result.fetchall()

        messages = []
        for row in rows:
            messages.append(_U2AAgentMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                message_type=row.message_type,
                content=row.content,
                json_content=row.json_content,
                status=row.status,
                session_task_id=row.session_task_id,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return messages


async def get_agent_messages_by_user(
    user_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> list[_U2AAgentMessage]:
    """根据用户ID获取所有代理消息

    Args:
        user_id: 用户ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        代理消息列表
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(QUERY_AGENT_MESSAGES_BY_USER), {"user_id_value": user_id})
        rows = result.fetchall()

        messages = []
        for row in rows:
            messages.append(_U2AAgentMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                message_type=row.message_type,
                content=row.content,
                json_content=row.json_content,
                status=row.status,
                session_task_id=row.session_task_id,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return messages


async def delete_agent_message(
    message_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """删除代理消息

    Args:
        message_id: 消息ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        删除是否成功（如果消息不存在，返回False）
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(DELETE_AGENT_MESSAGE), {"id_value": message_id})
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0


async def delete_agent_messages_by_session(
    session_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """删除指定会话的所有代理消息

    Args:
        session_id: 会话ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        删除是否成功
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(text(DELETE_AGENT_MESSAGES_BY_SESSION), {"session_id_value": session_id})
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0

async def delete_agent_messages_by_session_task(
    session_task_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """删除指定会话任务的所有代理消息

    Args:
        session_task_id: 会话任务ID
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        删除是否成功
    """
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(DELETE_AGENT_MESSAGES_BY_SESSION_TASK),
            {"session_task_id_value": session_task_id}
            )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount > 0

async def update_agent_message_status_by_ids(
    message_ids: list[UUID],
    new_status: Literal["streaming", "stop", "completed", "error"],
    ctx: SQL_OP_ContextData | None = None,
) -> int:
    """根据消息ID批量更新代理消息状态

    Args:
        message_ids: 消息ID列表
        new_status: 新的状态值
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        更新的消息数量
    """
    if not message_ids:
        return 0

    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(UPDATE_AGENT_MESSAGE_STATUS_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {
                "status_value": new_status,
                "ids_list": message_ids,
            },
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount


async def update_agent_message_session_task_by_ids(
    message_ids: list[UUID],
    session_task_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> int:
    """根据消息ID批量更新代理消息的session_task_id

    Args:
        message_ids: 消息ID列表
        session_task_id: 新的session_task_id值
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        更新的消息数量
    """
    if not message_ids:
        return 0

    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(UPDATE_AGENT_MESSAGE_SESSION_TASK_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {
                "session_task_id_value": session_task_id,
                "ids_list": message_ids,
            },
        )
        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return result.rowcount


async def get_agent_messages_by_session_task_ids(
    task_ids: list[UUID],
    ctx: SQL_OP_ContextData | None = None,
) -> list[_U2AAgentMessage]:
    """根据多个 session_task_id 批量查询代理消息

    Args:
        task_ids: session_task_id 列表
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        代理消息列表，按 session_task_id, sub_seq_index 排序
    """
    if not task_ids:
        return []
    async with _resolve_conn(ctx) as conn:
        result = await conn.execute(
            text(QUERY_AGENT_MESSAGES_BY_SESSION_TASK_IDS).bindparams(
                bindparam("task_ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {"task_ids_list": task_ids},
        )
        rows = result.fetchall()
        return [
            _U2AAgentMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                message_type=row.message_type,
                content=row.content,
                json_content=row.json_content,
                status=row.status,
                session_task_id=row.session_task_id,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]