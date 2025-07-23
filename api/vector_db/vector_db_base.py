from __future__ import annotations

from abc import ABC, abstractmethod

# import generic
from typing import Any, Generic, TypeVar

VDBObjectType = TypeVar("VDBObjectType")

class BaseVectorDB(ABC, Generic[VDBObjectType]):
    @abstractmethod
    def add_object(self, obj: VDBObjectType, **kwargs: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_objects(self, objs: list[VDBObjectType], **kwargs: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def id_exists(self, id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_by_ids(self, ids: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search_ids_by_metadata_field(self, key: str, value: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def delete_by_metadata_field(self, key: str, value: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def search_by_vector(self,
                         query_vector: list[float] | dict[str, list[float]],
                         **kwargs: dict[str, Any]) -> list[VDBObjectType]:
        raise NotImplementedError

    @abstractmethod
    def search_by_text(self,
                       query: str | dict[str, str],
                       **kwargs: dict[str, Any]) -> list[VDBObjectType]:
        raise NotImplementedError

class AsyncBaseVectorDB(ABC, Generic[VDBObjectType]):

    @abstractmethod
    async def add_object(self, obj: VDBObjectType, **kwargs: dict[str, Any]) -> None:
        raise NotImplementedError
    
    @abstractmethod
    async def add_objects(self, objs: list[VDBObjectType], **kwargs: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def id_exists(self, id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_ids(self, ids: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def search_ids_by_metadata_field(self, key: str, value: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_metadata_field(self, key: str, value: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def search_by_vector(self,
                         query_vector: list[float] | dict[str, list[float]],
                         **kwargs: dict[str, Any]) -> list[VDBObjectType]:
        raise NotImplementedError

    @abstractmethod
    async def search_by_text(self,
                       query: str | dict[str, str],
                       **kwargs: dict[str, Any]) -> list[VDBObjectType]:
        raise NotImplementedError
