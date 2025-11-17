from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, List, Union
from uuid import UUID
from datetime import datetime

from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import ARRAY, UUID as SQLTYPE_UUID , INTEGER, JSONB, TEXT, VARCHAR

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file
import ujson

sql_file_path = Path(__file__).parent / "a2a_session_side_msg.sql"

sql_statements = parse_sql_file(sql_file_path)


CREATE_SIDE_MESSAGE_TABLE = sql_statements["CreatTable"]

INSERT_SIDE_MESSAGE = sql_statements["InsertSideMessage"]
INSERT_SIDE_MESSAGES_BATCH = sql_statements["InsertSideMessagesBatch"]

UPDATE_SIDE_MESSAGE_1 = sql_statements["UpdateSideMessage1"]
UPDATE_SIDE_MESSAGE_2 = sql_statements["UpdateSideMessage2"]
UPDATE_SIDE_MESSAGE_3 = sql_statements["UpdateSideMessage3"]
UPDATE_SIDE_MESSAGE_SESSION_TASK_BY_IDS = sql_statements["UpdateSideMessageSessionTaskByIds"]

CHECK_SIDE_MESSAGE_EXISTS = sql_statements["SideMessageExists"]
QUERY_SIDE_MESSAGE_BY_ID = sql_statements["QuerySideMessageById"]
QUERY_SIDE_MESSAGES_BY_SESSION = sql_statements["QuerySideMessagesBySession"]
QUERY_SIDE_MESSAGES_BY_SESSION_TASK = sql_statements["QuerySideMessagesBySessionTask"]
QUERY_SIDE_MESSAGE_FIELD_1 = sql_statements["QuerySideMessageField1"]
QUERY_SIDE_MESSAGE_FIELD_2 = sql_statements["QuerySideMessageField2"]
QUERY_SIDE_MESSAGE_FIELD_3 = sql_statements["QuerySideMessageField3"]
QUERY_SIDE_MESSAGE_FIELD_4 = sql_statements["QuerySideMessageField4"]
DELETE_SIDE_MESSAGE = sql_statements["DeleteSideMessage"]
DELETE_SIDE_MESSAGES_BY_SESSION = sql_statements["DeleteSideMessagesBySession"]
DELETE_SIDE_MESSAGES_BY_SESSION_TASK = sql_statements["DeleteSideMessagesBySessionTask"]
GET_NEXT_SIDE_MESSAGE_SEQ_INDEX = sql_statements["GetNextSideMessageSeqIndex"]


@dataclass
class _A2ASessionSideMessage:
    """A2A会话侧边消息数据模型"""
    id: UUID
    session_id: UUID
    session_task_id: UUID
    seq_index: int
    message_type: str
    content: str
    created_at: datetime
    json_content: dict[str, Any] | None


@dataclass
class _A2ASessionSideMessageCreate:
    """创建A2A会话侧边消息的数据模型"""
    session_id: UUID
    session_task_id: UUID
    seq_index: int
    message_type: str
    content: str
    json_content: dict[str, Any] | None = None


@dataclass
class _A2ASessionSideMessageBatchCreate:
    """批量创建A2A会话侧边消息的数据模型"""
    session_ids: list[UUID]
    session_task_ids: list[UUID]
    seq_indices: list[int]
    message_types: list[str]
    contents: list[str]
    json_contents: list[dict[str, Any] | None]


@dataclass
class _A2ASessionSideMessageUpdate:
    """更新A2A会话侧边消息的数据模型"""
    message_id: UUID
    fields: dict[
        Literal["session_id", "session_task_id", "seq_index", "message_type", "content", "json_content"],
        UUID | str | int | dict[str, Any],
    ]


async def create_tables() -> None:
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_SIDE_MESSAGE_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()


def _get_table_name(side: Literal["A", "B"]) -> str:
    """根据侧边获取表名

    Args:
        side: 侧边标识，"A" 或 "B"

    Returns:
        表名

    Raises:
        ValueError: 如果side不是"A"或"B"
    """
    if side == "A":
        return "a2a_session_A_side_msg"
    elif side == "B":
        return "a2a_session_B_side_msg"
    else:
        raise ValueError(f"Invalid side: {side}. Must be 'A' or 'B'")

async def insert_side_message(
    side: Literal["A", "B"],
    message_data: _A2ASessionSideMessageCreate,
) -> UUID:
    """插入新的A2A会话侧边消息

    Args:
        side: 侧边标识，"A" 或 "B"
        message_data: 消息创建数据

    Returns:
        新消息的ID
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SIDE_MESSAGE).bindparams(table_name=table_name),
            {
                "session_id": message_data.session_id,
                "session_task_id": message_data.session_task_id,
                "seq_index": message_data.seq_index,
                "message_type": message_data.message_type,
                "content": message_data.content,
                "json_content": message_data.json_content,
            },
        )
        await conn.commit()
        return result.scalar()


async def insert_side_messages_batch(
    side: Literal["A", "B"],
    messages_data: _A2ASessionSideMessageBatchCreate,
) -> list[UUID]:
    """批量插入A2A会话侧边消息

    Args:
        side: 侧边标识，"A" 或 "B"
        messages_data: 批量消息创建数据

    Returns:
        新消息的ID列表

    Raises:
        ValueError: 如果输入的列表长度不一致
    """
    # 验证所有列表长度一致
    list_lengths = [
        len(messages_data.session_ids),
        len(messages_data.session_task_ids),
        len(messages_data.seq_indices),
        len(messages_data.message_types),
        len(messages_data.contents),
        len(messages_data.json_contents),
    ]

    if len(set(list_lengths)) != 1:
        raise ValueError(f"All input lists must have the same length. Got lengths: {list_lengths}")

    if list_lengths[0] == 0:
        return []

    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SIDE_MESSAGES_BATCH).bindparams(
                bindparam("session_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("session_task_ids_list", type_=ARRAY(SQLTYPE_UUID)),
                bindparam("seq_indices_list", type_=ARRAY(INTEGER)),
                bindparam("message_types_list", type_=ARRAY(VARCHAR)),
                bindparam("contents_list", type_=ARRAY(TEXT)),
                bindparam("json_contents_list", type_=ARRAY(JSONB)),
                table_name=table_name,
            ),
            {
                "session_ids_list": messages_data.session_ids,
                "session_task_ids_list": messages_data.session_task_ids,
                "seq_indices_list": messages_data.seq_indices,
                "message_types_list": messages_data.message_types,
                "contents_list": messages_data.contents,
                "json_contents_list": [ujson.dumps(json_content, ensure_ascii=False) for json_content in messages_data.json_contents],
            },
        )
        await conn.commit()
        return [row[0] for row in result.fetchall()]


async def insert_side_messages_from_list(
    side: Literal["A", "B"],
    messages: list[_A2ASessionSideMessageCreate],
) -> list[UUID]:
    """从单个消息列表批量插入A2A会话侧边消息

    Args:
        side: 侧边标识，"A" 或 "B"
        messages: 单个消息创建数据列表

    Returns:
        新消息的ID列表
    """
    if not messages:
        return []

    batch_data = _A2ASessionSideMessageBatchCreate(
        session_ids=[msg.session_id for msg in messages],
        session_task_ids=[msg.session_task_id for msg in messages],
        seq_indices=[msg.seq_index for msg in messages],
        message_types=[msg.message_type for msg in messages],
        contents=[msg.content for msg in messages],
        json_contents=[msg.json_content for msg in messages],
    )

    return await insert_side_messages_batch(side, batch_data)


async def get_next_side_message_seq_index(
    side: Literal["A", "B"],
    session_id: UUID,
) -> int:
    """获取会话的下一条侧边消息序列索引

    Args:
        side: 侧边标识，"A" 或 "B"
        session_id: 会话ID

    Returns:
        下一条侧边消息的序列索引
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_NEXT_SIDE_MESSAGE_SEQ_INDEX).bindparams(table_name=table_name),
            {"session_id": session_id},
        )
        return result.scalar()


async def update_side_message_fields(update_data: _A2ASessionSideMessageUpdate) -> bool:
    """更新侧边消息字段

    Args:
        update_data: 消息更新数据

    Returns:
        更新是否成功
    """
    field_count = len(update_data.fields)

    if field_count == 0:
        return False
    elif field_count == 1:
        sql = UPDATE_SIDE_MESSAGE_1
    elif field_count == 2:
        sql = UPDATE_SIDE_MESSAGE_2
    elif field_count == 3:
        sql = UPDATE_SIDE_MESSAGE_3
    else:
        error_msg = f"Unsupported field count: {field_count}"
        raise ValueError(error_msg)

    # 这里需要知道是哪张表，需要从其他地方获取side信息
    # 暂时使用placeholder，实际使用时需要传入side参数或修改设计
    # table_name = _get_table_name(side)

    params = {"id_value": update_data.message_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        # 暂时无法确定table_name，这里需要外部提供side信息
        # result = await conn.execute(text(sql).bindparams(table_name=table_name), params)
        # await conn.commit()
        # return result.rowcount > 0
        raise NotImplementedError("update_side_message_fields requires side parameter")


async def check_side_message_exists(side: Literal["A", "B"], message_id: UUID) -> bool:
    """检查侧边消息是否存在

    Args:
        side: 侧边标识，"A" 或 "B"
        message_id: 消息ID

    Returns:
        消息是否存在
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(CHECK_SIDE_MESSAGE_EXISTS).bindparams(table_name=table_name),
            {"id_value": message_id},
        )
        count = result.scalar()
        return count > 0


async def get_side_message_by_id(side: Literal["A", "B"], message_id: UUID) -> _A2ASessionSideMessage | None:
    """获取侧边消息信息

    Args:
        side: 侧边标识，"A" 或 "B"
        message_id: 消息ID

    Returns:
        消息信息，如果不存在则返回None
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SIDE_MESSAGE_BY_ID).bindparams(table_name=table_name),
            {"id_value": message_id},
        )
        row = result.first()

        if row is None:
            return None

        return _A2ASessionSideMessage(
            id=row.id,
            session_id=row.session_id,
            session_task_id=row.session_task_id,
            seq_index=row.seq_index,
            message_type=row.message_type,
            content=row.content,
            json_content=row.json_content,
            created_at=row.created_at,
        )


async def get_side_messages_by_session(side: Literal["A", "B"], session_id: UUID) -> list[_A2ASessionSideMessage]:
    """根据会话ID获取所有侧边消息

    Args:
        side: 侧边标识，"A" 或 "B"
        session_id: 会话ID

    Returns:
        侧边消息列表
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SIDE_MESSAGES_BY_SESSION).bindparams(table_name=table_name),
            {"session_id_value": session_id},
        )
        rows = result.fetchall()

        messages = []
        for row in rows:
            messages.append(_A2ASessionSideMessage(
                id=row.id,
                session_id=row.session_id,
                session_task_id=row.session_task_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                json_content=row.json_content,
                created_at=row.created_at,
            ))

        return messages


async def get_side_messages_by_session_task(
    side: Literal["A", "B"],
    session_task_id: UUID,
) -> list[_A2ASessionSideMessage]:
    """根据会话任务ID获取侧边消息

    Args:
        side: 侧边标识，"A" 或 "B"
        session_task_id: 会话任务ID

    Returns:
        侧边消息列表
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SIDE_MESSAGES_BY_SESSION_TASK).bindparams(table_name=table_name),
            {"session_task_id_value": session_task_id},
        )
        rows = result.fetchall()

        messages = []
        for row in rows:
            messages.append(_A2ASessionSideMessage(
                id=row.id,
                session_id=row.session_id,
                session_task_id=row.session_task_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                json_content=row.json_content,
                created_at=row.created_at,
            ))

        return messages


async def get_side_message_field(
    side: Literal["A", "B"],
    message_id: UUID,
    field_name: Literal["id", "session_id", "session_task_id", "seq_index", "message_type", "content", "json_content", "created_at"],
) -> UUID | int | str | dict[str, Any] | datetime | None:
    """获取侧边消息的单个字段值

    Args:
        side: 侧边标识，"A" 或 "B"
        message_id: 消息ID
        field_name: 字段名

    Returns:
        字段值，如果消息不存在则返回None
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SIDE_MESSAGE_FIELD_1).bindparams(table_name=table_name),
            {"id_value": message_id, "field_name_1": field_name},
        )
        return result.scalar()


async def get_side_message_fields(
    side: Literal["A", "B"],
    message_id: UUID,
    field_names: list[Literal["id", "session_id", "session_task_id", "seq_index", "message_type", "content", "json_content", "created_at"]],
) -> dict[Literal["id", "session_id", "session_task_id", "seq_index", "message_type", "content", "json_content", "created_at"], UUID | int | str | dict[str, Any] | datetime] | None:
    """获取侧边消息的多个字段值

    Args:
        side: 侧边标识，"A" 或 "B"
        message_id: 消息ID
        field_names: 字段名列表

    Returns:
        字段值字典，如果消息不存在则返回None
    """
    field_count = len(field_names)

    if field_count == 0:
        return {}
    elif field_count == 1:
        sql = QUERY_SIDE_MESSAGE_FIELD_1
    elif field_count == 2:
        sql = QUERY_SIDE_MESSAGE_FIELD_2
    elif field_count == 3:
        sql = QUERY_SIDE_MESSAGE_FIELD_3
    elif field_count == 4:
        sql = QUERY_SIDE_MESSAGE_FIELD_4
    else:
        error_msg = f"Unsupported field count: {field_count}"
        raise ValueError(error_msg)

    table_name = _get_table_name(side)

    params = {"id_value": message_id}
    for i, field_name in enumerate(field_names, 1):
        params[f"field_name_{i}"] = field_name

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql).bindparams(table_name=table_name), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}


async def delete_side_message(side: Literal["A", "B"], message_id: UUID) -> bool:
    """删除侧边消息

    Args:
        side: 侧边标识，"A" 或 "B"
        message_id: 消息ID

    Returns:
        删除是否成功（如果消息不存在，返回False）
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_SIDE_MESSAGE).bindparams(table_name=table_name),
            {"id_value": message_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def delete_side_messages_by_session(side: Literal["A", "B"], session_id: UUID) -> bool:
    """删除指定会话的所有侧边消息

    Args:
        side: 侧边标识，"A" 或 "B"
        session_id: 会话ID

    Returns:
        删除是否成功
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_SIDE_MESSAGES_BY_SESSION).bindparams(table_name=table_name),
            {"session_id_value": session_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def delete_side_messages_by_session_task(side: Literal["A", "B"], session_task_id: UUID) -> bool:
    """删除指定会话任务的所有侧边消息

    Args:
        side: 侧边标识，"A" 或 "B"
        session_task_id: 会话任务ID

    Returns:
        删除是否成功
    """
    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_SIDE_MESSAGES_BY_SESSION_TASK).bindparams(table_name=table_name),
            {"session_task_id_value": session_task_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def update_side_message_session_task_by_ids(
    side: Literal["A", "B"],
    message_ids: list[UUID],
    session_task_id: UUID | None,
) -> int:
    """根据消息ID批量更新侧边消息的session_task_id

    Args:
        side: 侧边标识，"A" 或 "B"
        message_ids: 消息ID列表
        session_task_id: 新的session_task_id值，如果为None则清除关联

    Returns:
        更新的消息数量
    """
    if not message_ids:
        return 0

    table_name = _get_table_name(side)

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SIDE_MESSAGE_SESSION_TASK_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
                table_name=table_name,
            ),
            {
                "session_task_id_value": session_task_id,
                "ids_list": message_ids,
            },
        )
        await conn.commit()
        return result.rowcount
