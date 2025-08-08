from abc import ABC, abstractmethod
from .data_model import UserBase
from typing import Any

class UserDBBase(ABC):
    @abstractmethod
    def create_user(self, username: str, password: str) -> None:
        pass

    @abstractmethod
    def get_user(self, username: str) -> UserBase:
        pass

    @abstractmethod
    def update_user(self, **kwargs: dict[str, Any]) -> None:
        pass

    @abstractmethod
    def delete_user(self, username: str) -> None:
        pass