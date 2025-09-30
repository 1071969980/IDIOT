from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, Literal
from uuid import uuid4
from sqlalchemy import text, Row
from sqlalchemy.ext.asyncio import AsyncConnection

from api.sql_orm_models import ASYNC_SQL_ENGINE
from api.sql_orm_models.utils import parse_sql_file, now_str
from pathlib import Path


sql_file_path = Path(__file__).parent / "UserTable.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements["CreateTable"]

INSERT_USER = sql_statements["InsertUser"]

UPDATE_USER1 = sql_statements["UpdateUser1"]
UPDATE_USER2 = sql_statements["UpdateUser2"]
UPDATE_USER3 = sql_statements["UpdateUser3"]

IS_EXISTS = sql_statements["IsExists"]
QUERY_USER_UUID_BY_NAME = sql_statements["QueryUserUUIDByName"]
QUERY_USER = sql_statements["QueryUser"]
QUERY_FIELD1 = sql_statements["QueryField1"]
QUERY_FIELD2 = sql_statements["QueryField2"]
QUERY_FIELD3 = sql_statements["QueryField3"]
QUERY_FIELD4 = sql_statements["QueryField4"]
DELETE_USER = sql_statements["DeleteUser"]


@dataclass
class _User:
    """用户数据模型"""
    id: int
    uuid: str
    user_name: str
    create_time: str
    is_deleted: bool
    hashed_password: str


@dataclass
class _UserCreate:
    """创建用户的数据模型"""
    user_name: str
    hashed_password: str
    uuid: Optional[str] = None


@dataclass
class _UserUpdate:
    """更新用户的数据模型"""
    uuid: str
    fields: Dict[
        Literal["user_name", "create_time", "is_deleted", "hashed_password"],
        Union[str, bool]
    ]


async def create_table() -> None:
    """创建用户表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(CREATE_TABLE))
        await conn.commit()


async def insert_user(user_data: _UserCreate) -> str:
    """插入新用户

    Args:
        user_data: 用户创建数据

    Returns:
        新用户的UUID
    """
    if user_data.uuid is None:
        user_data.uuid = str(uuid4())

    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(
            text(INSERT_USER),
            {
                "uuid": user_data.uuid,
                "user_name": user_data.user_name,
                "hashed_password": user_data.hashed_password
            }
        )
        await conn.commit()
        return user_data.uuid


async def update_user_fields(update_data: _UserUpdate) -> bool:
    """更新用户字段

    Args:
        update_data: 用户更新数据

    Returns:
        更新是否成功
    """
    field_count = len(update_data.fields)

    if field_count == 0:
        return False
    elif field_count == 1:
        sql = UPDATE_USER1
    elif field_count == 2:
        sql = UPDATE_USER2
    elif field_count == 3:
        sql = UPDATE_USER3
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"uuid_value": update_data.uuid}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0


async def user_exists(uuid: str) -> bool:
    """检查用户是否存在

    Args:
        uuid: 用户UUID

    Returns:
        用户是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(IS_EXISTS), {"uuid_value": uuid})
        count = result.scalar()
        return count > 0


async def get_user_uuid_by_name(user_name: str) -> Optional[str]:
    """根据用户名获取用户UUID

    Args:
        user_name: 用户名

    Returns:
        用户UUID，如果用户不存在或已删除则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER_UUID_BY_NAME), {"user_name": user_name})
        return result.scalar()


async def get_user(uuid: str) -> Optional[_User]:
    """获取用户信息

    Args:
        uuid: 用户UUID

    Returns:
        用户信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER), {"uuid_value": uuid})
        row = result.first()

        if row is None:
            return None

        return _User(
            id=row.id,
            uuid=row.uuid,
            user_name=row.user_name,
            create_time=row.create_time,
            is_deleted=row.is_deleted,
            hashed_password=row.hashed_password
        )


async def get_user_field(
    uuid: str,
    field_name: Literal["id", "uuid", "user_name", "create_time", "is_deleted", "hashed_password"]
) -> Optional[Union[int, str, bool]]:
    """获取用户的单个字段值

    Args:
        uuid: 用户UUID
        field_name: 字段名

    Returns:
        字段值，如果用户不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_FIELD1),
            {"uuid_value": uuid, "field_name_1": field_name}
        )
        return result.scalar()


async def get_user_fields(
    uuid: str,
    field_names: list[Literal["id", "uuid", "user_name", "create_time", "is_deleted", "hashed_password"]]
) -> Optional[Dict[
    Literal["id", "uuid", "user_name", "create_time", "is_deleted", "hashed_password"],
    Union[int, str, bool]
]]:
    """获取用户的多个字段值

    Args:
        uuid: 用户UUID
        field_names: 字段名列表

    Returns:
        字段值字典，如果用户不存在则返回None
    """
    field_count = len(field_names)

    if field_count == 0:
        return {}
    elif field_count == 1:
        sql = QUERY_FIELD1
    elif field_count == 2:
        sql = QUERY_FIELD2
    elif field_count == 3:
        sql = QUERY_FIELD3
    elif field_count == 4:
        sql = QUERY_FIELD4
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"uuid_value": uuid}
    for i, field_name in enumerate(field_names, 1):
        params[f"field_name_{i}"] = field_name

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}


async def delete_user(uuid: str) -> bool:
    """软删除用户（将is_deleted设置为true）

    Args:
        uuid: 用户UUID

    Returns:
        删除是否成功（如果用户不存在或已删除，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_USER), {"uuid_value": uuid})
        await conn.commit()
        return result.rowcount > 0

