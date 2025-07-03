from api.llm.deepseek import async_client as deepseek_async_client
from api.llm.qwen import async_client as qwen_async_client

from .load_balancer import LoadBalancer
from .service_instance import AsyncOpenAIServiceInstance
from .service_regeistry import ServiceConfig, ServiceRegistry

LOAD_BLANCER = LoadBalancer(ServiceRegistry())

DEEPSEEK_REASONER_SERVICE_NAME = "deepseek"

def register_deepseek_service() -> None:
    service_reg = LOAD_BLANCER.registry
    # tongyi service for deepseek
    tongyi_instance = AsyncOpenAIServiceInstance(
        name="tongyi",
        openai_client=qwen_async_client(),
        model="deepseek-r1-0528",
    )
    service_reg.register_service(DEEPSEEK_REASONER_SERVICE_NAME,
                                 tongyi_instance)

    # deepseek offical service
    deepseek_offcial_instance = AsyncOpenAIServiceInstance(
        name="deepseek",
        openai_client=deepseek_async_client(),
        model="deepseek-reasoner",
    )
    service_reg.register_service(DEEPSEEK_REASONER_SERVICE_NAME,
                                 deepseek_offcial_instance)
    
register_deepseek_service()

