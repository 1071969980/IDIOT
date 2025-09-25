from abc import ABC, abstractmethod
from .data_model import UserModel
from typing import Any, Optional


class UserDBBase(ABC):
    @abstractmethod
    async def create_user(self, username: str, password: str, *args, **kwargs) -> str:
        pass

    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        pass

    @abstractmethod
    async def get_user_by_uuid(self, uuid: str) -> Optional[UserModel]:
        pass

    @abstractmethod
    async def update_user(self, uuid: str, user_name: str | None = None, password: str | None = None, *args, **kwargs) -> None:
        pass

    @abstractmethod
    async def delete_user(self, uuid: str, *args, **kwargs) -> bool:
        pass
