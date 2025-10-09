
from .constant import PWD_CONTEXT
from .sql_stat.utils import insert_user, get_user, update_user_fields, delete_user, get_user_id_by_name, _UserCreate, _UserUpdate, _User
from .user_db_base import UserDBBase
from typing import Optional, Any
from uuid import UUID

class SimpleUserDB(UserDBBase):
    async def create_user(self, username: str, password: str, *args, **kwargs) -> UUID:
        hashed_password = PWD_CONTEXT.hash(password)
        user_data = _UserCreate(
            user_name=username,
            hashed_password=hashed_password
        )
        user_id = await insert_user(user_data)
        return user_id

    async def get_user_by_username(self, username: str) -> Optional[_User]:
        user_id = await get_user_id_by_name(username)
        if not user_id:
            return None

        return await get_user(user_id)

    async def get_user_by_uuid(self, uuid_str: str) -> Optional[_User]:
        from uuid import UUID
        user_id = UUID(uuid_str)
        return await get_user(user_id)

    async def update_user(self,
                    uuid_str: str,
                    user_name: str | None = None,
                    password: str | None = None,
                    *args,
                    **kwargs):
        from uuid import UUID
        update_fields: dict[str, Any] = {}
        if user_name is not None:
            update_fields["user_name"] = user_name
        if password is not None:
            update_fields["hashed_password"] = PWD_CONTEXT.hash(password)

        if update_fields:
            user_id = UUID(uuid_str)
            update_data = _UserUpdate(id=user_id, fields=update_fields)
            await update_user_fields(update_data)

    async def delete_user(self, uuid_str: str, *args, **kwargs):
        from uuid import UUID
        user_id = UUID(uuid_str)
        return await delete_user(user_id)
        
