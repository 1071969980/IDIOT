from abc import ABC, abstractmethod
from .data_model import UserBase
from typing import Any


class UserDBBase(ABC):
    @abstractmethod
    def create_user(self, username: str, password: str, *args, **kwargs) -> None:
        pass

    @abstractmethod
    def get_user(self, username: str, *args, **kwargs) -> UserBase|None:
        pass

    @abstractmethod
    def update_user(self, *args, **kwargs: dict[str, Any]) -> None:
        pass

    @abstractmethod
    def delete_user(self, uuid: str, *args, **kwargs) -> None:
        pass
