from api.llm.tongyi import async_client as tongyi_async_client

from ..constant import (
    QWEN_MAX_SERVICE_NAME,
    QWEN_PLUS_SERVICE_NAME,
    LOAD_BLANCER,
)
from ..service_instance import AsyncOpenAIServiceInstance

def register_qwen_max_service() -> None:
    service_reg = LOAD_BLANCER.registry
    # tongyi service for qwen max
    tongyi_instance = AsyncOpenAIServiceInstance(
        name="tongyi",
        openai_client=tongyi_async_client(),
        model="qwen-max",
    )
    service_reg.register_service(QWEN_MAX_SERVICE_NAME,
                                 tongyi_instance)
    
def register_qwen_plus_service() -> None:
    service_reg = LOAD_BLANCER.registry
    # tongyi service for qwen plus
    tongyi_instance = AsyncOpenAIServiceInstance(
        name="tongyi",
        openai_client=tongyi_async_client(),
        model="qwen-plus",
    )
    service_reg.register_service(
        QWEN_PLUS_SERVICE_NAME,
        tongyi_instance,
    )