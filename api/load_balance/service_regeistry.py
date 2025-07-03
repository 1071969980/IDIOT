from abc import ABC, abstractmethod
import random
import time
import requests
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from .service_instance import ServiceInstanceBase


class ServiceConfig:
    """服务特定配置容器"""
    def __init__(
        self,
        max_retries: int = 100,            # 默认最大重试次数
        retry_delay: float = 2,        # 重试基础延迟(秒)
        retry_backoff: float = 1.1,      # 退避因子
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff

class ServiceRegistry:
    """服务注册中心"""
    def __init__(self):
        self._services: dict[str, list[ServiceInstanceBase]] = {}
        self._configs: dict[str, ServiceConfig] = {}
    
    def register_service(
        self,
        service_name: str,
        instance: ServiceInstanceBase,
        config: ServiceConfig | None = None,
    ):
        if service_name in self._services:
            self._services[service_name].append(instance)
        else:
            self._services[service_name] = [instance]
        self._configs[service_name] = config if config else ServiceConfig()
    
    def get_instances(self, service_name: str) -> list[ServiceInstanceBase]:
        return self._services.get(service_name, [])
    
    def get_config(self, service_name: str) -> ServiceConfig:
        return self._configs.get(service_name, ServiceConfig())

