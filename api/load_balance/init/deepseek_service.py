from api.llm.deepseek import async_client as deepseek_async_client
from api.llm.tongyi import async_client as tongyi_async_client

from ..constant import (
    DEEPSEEK_REASONER_SERVICE_NAME,
    LOAD_BLANCER,
)
from ..service_instance import AsyncOpenAIServiceInstance


def register_deepseek_reasoner_service() -> None:
    service_reg = LOAD_BLANCER.registry
    # tongyi service for deepseek
    # tongyi_instance = AsyncOpenAIServiceInstance(
    #     name="tongyi",
    #     openai_client=tongyi_async_client(),
    #     model="deepseek-r1-0528",
    # )
    # service_reg.register_service(DEEPSEEK_REASONER_SERVICE_NAME,
    #                              tongyi_instance)

    # deepseek offical service
    deepseek_offcial_instance = AsyncOpenAIServiceInstance(
        name="deepseek",
        openai_client=deepseek_async_client(),
        model="deepseek-reasoner",
    )
    service_reg.register_service(DEEPSEEK_REASONER_SERVICE_NAME,
                                 deepseek_offcial_instance)
