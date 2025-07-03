from .load_balancer import LoadBalancer
from .service_instance import AsyncOpenAIServiceInstance
from .service_regeistry import ServiceConfig, ServiceRegistry

LOAD_BLANCER = LoadBalancer(ServiceRegistry())

DEEPSEEK_REASONER_SERVICE_NAME = "deepseek"