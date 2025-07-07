from .load_balancer import LoadBalancer
from .service_instance import AsyncOpenAIServiceInstance
from .service_regeistry import ServiceConfig, ServiceRegistry

__all__ = [
    "DEEPSEEK_REASONER_SERVICE_NAME",
    "LOAD_BLANCER",
    "QWEN_MAX_SERVICE_NAME",
    "QWEN_PLUS_SERVICE_NAME",
]

LOAD_BLANCER = LoadBalancer(ServiceRegistry())

DEEPSEEK_REASONER_SERVICE_NAME = "deepseek"
QWEN_MAX_SERVICE_NAME = "qwen-max"
QWEN_PLUS_SERVICE_NAME = "qwen-plus"