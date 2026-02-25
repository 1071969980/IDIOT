from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Any
from pydantic import BaseModel

InputModel = TypeVar('InputModel', bound=BaseModel)
OutputModel = TypeVar('OutputModel', bound=BaseModel)

class AbstractCommand(ABC, Generic[InputModel, OutputModel]):
    def __init__(self, input_model: InputModel):
        self.input_model = input_model

    @abstractmethod
    async def execute(self) -> OutputModel:
        pass

    async def rollback(self) -> OutputModel:
        """
        回滚方法，仅供内部使用，在异常时自动调用
        默认抛出NotImplementedError，子类可以选择实现
        """
        raise NotImplementedError("Rollback not implemented for this command")