from typing import Any

from openai import AsyncOpenAI


class ServiceInstanceBase:
    """外部服务实例表示"""
    def __init__(self, name: str, **kwargs: dict[str, Any]) -> None:
        self.name = name
        self.meta_data: dict[str, Any] = kwargs if kwargs else {}

class AsyncOpenAIServiceInstance(ServiceInstanceBase):
    def __init__(self, name: str,
                 openai_client: AsyncOpenAI,
                 **kwargs: dict[str, Any]) -> None:
        super().__init__(name, **kwargs)
        self.client: AsyncOpenAI = openai_client
