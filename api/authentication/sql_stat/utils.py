from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, Literal
from uuid import UUID, uuid4
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
UPDATE_USER4 = sql_statements["UpdateUser4"]

IS_EXISTS = sql_statements["IsExists"]
QUERY_USER_ID_BY_NAME = sql_statements["QueryUserIDByName"]
QUERY_USER = sql_statements["QueryUser"]
QUERY_USER_BY_USERNAME = sql_statements["QueryUserByUsername"]
QUERY_FIELD1 = sql_statements["QueryField1"]
QUERY_FIELD2 = sql_statements["QueryField2"]
QUERY_FIELD3 = sql_statements["QueryField3"]
QUERY_FIELD4 = sql_statements["QueryField4"]
DELETE_USER = sql_statements["DeleteUser"]


@dataclass
class _User:
    """用户数据模型"""
    id: UUID
    user_name: str
    create_time: str
    is_deleted: bool
    hashed_password: str
    salt: str


@dataclass
class _UserCreate:
    """创建用户的数据模型"""
    user_name: str
    hashed_password: str
    salt: str


@dataclass
class _UserUpdate:
    """更新用户的数据模型"""
    id: UUID
    fields: Dict[
        Literal["user_name", "create_time", "is_deleted", "hashed_password", "salt"],
        Union[str, bool]
    ]


async def create_table() -> None:
    """创建用户表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(CREATE_TABLE))
        await conn.commit()


async def insert_user(user_data: _UserCreate) -> UUID:
    """插入新用户

    Args:
        user_data: 用户创建数据

    Returns:
        新用户的ID
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_USER),
            {
                "user_name": user_data.user_name,
                "hashed_password": user_data.hashed_password,
                "salt": user_data.salt
            }
        )
        await conn.commit()

        # 从RETURNING子句获取插入的UUID并转换为正确的类型
        return result.scalar()


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
    elif field_count == 4:
        sql = UPDATE_USER4
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"id_value": update_data.id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0


async def user_exists(id: UUID | str) -> bool:
    """检查用户是否存在

    Args:
        id: 用户ID

    Returns:
        用户是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(IS_EXISTS), {"id_value": id})
        count = result.scalar()
        return count > 0


async def get_user_id_by_name(user_name: str) -> Optional[UUID]:
    """根据用户名获取用户ID

    Args:
        user_name: 用户名

    Returns:
        用户ID，如果用户不存在或已删除则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER_ID_BY_NAME), {"user_name": user_name})
        return result.scalar()


async def get_user_by_username(user_name: str) -> Optional[_User]:
    """根据用户名获取用户信息

    Args:
        user_name: 用户名

    Returns:
        用户信息，如果不存在或已删除则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER_BY_USERNAME), {"user_name": user_name})
        row = result.first()

        if row is None:
            return None

        return _User(
            id=row.id,
            user_name=row.user_name,
            create_time=row.create_time,
            is_deleted=row.is_deleted,
            hashed_password=row.hashed_password,
            salt=row.salt
        )


async def get_user(id: UUID | str) -> Optional[_User]:
    """获取用户信息

    Args:
        id: 用户ID

    Returns:
        用户信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER), {"id_value": id})
        row = result.first()

        if row is None:
            return None

        return _User(
            id=row.id,
            user_name=row.user_name,
            create_time=row.create_time,
            is_deleted=row.is_deleted,
            hashed_password=row.hashed_password,
            salt=row.salt
        )


async def get_user_field(
    id: UUID,
    field_name: Literal["id", "user_name", "create_time", "is_deleted", "hashed_password", "salt"]
) -> Optional[Union[UUID, str, bool]]:
    """获取用户的单个字段值

    Args:
        id: 用户ID
        field_name: 字段名

    Returns:
        字段值，如果用户不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_FIELD1),
            {"id_value": id, "field_name_1": field_name}
        )
        return result.scalar()


async def get_user_fields(
    id: UUID,
    field_names: list[Literal["id", "user_name", "create_time", "is_deleted", "hashed_password", "salt"]]
) -> Optional[Dict[
    Literal["id", "user_name", "create_time", "is_deleted", "hashed_password", "salt"],
    Union[UUID, str, bool]
]]:
    """获取用户的多个字段值

    Args:
        id: 用户ID
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

    params = {"id_value": id}
    for i, field_name in enumerate(field_names, 1):
        params[f"field_name_{i}"] = field_name

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}


async def delete_user(user_id: UUID) -> bool:
    """软删除用户（将is_deleted设置为true）

    Args:
        user_id: 用户ID

    Returns:
        删除是否成功（如果用户不存在或已删除，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_USER), {"id_value": user_id})
        await conn.commit()
        return result.rowcount > 0

