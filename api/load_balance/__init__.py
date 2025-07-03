from .service_regeistry import ServiceConfig, ServiceRegistry
from .load_balancer import LoadBalancer

LOAD_BLANCER = LoadBalancer(ServiceRegistry())

