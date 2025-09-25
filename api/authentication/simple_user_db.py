
from .constant import PWD_CONTEXT
from .sql_stat.utils import insert_user, get_user, get_user_fields, update_user_fields, delete_user, _UserCreate, _UserUpdate
from .data_model import UserModel
from .user_db_base import UserDBBase
from typing import Optional, Any

class SimpleUserDB(UserDBBase):
    async def create_user(self, username: str, password: str, *args, **kwargs) -> str:
        hashed_password = PWD_CONTEXT.hash(password)
        user_data = _UserCreate(
            user_name=username,
            hashed_password=hashed_password
        )
        return await insert_user(user_data)

    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        user = await get_user_fields(username, ["uuid", "user_name", "hashed_password", "is_deleted"])
        if not user:
            return None
        return UserModel(
            username=user["user_name"],
            hashed_password=user["hashed_password"],
            disabled=user["is_deleted"],
        )

    async def get_user_by_uuid(self, uuid: str) -> Optional[UserModel]:
        user = await get_user(uuid)
        if not user:
            return None
        return UserModel(
            username=user.user_name,
            hashed_password=user.hashed_password,
            disabled=user.is_deleted,
        )

    async def update_user(self,
                    uuid: str,
                    user_name: str | None = None,
                    password: str | None = None,
                    *args,
                    **kwargs):
        update_fields: dict[str, Any] = {}
        if user_name is not None:
            update_fields["user_name"] = user_name
        if password is not None:
            update_fields["hashed_password"] = PWD_CONTEXT.hash(password)

        if update_fields:
            update_data = _UserUpdate(uuid=uuid, fields=update_fields)
            await update_user_fields(update_data)

    async def delete_user(self, uuid: str, *args, **kwargs):
        return await delete_user(uuid)
        
