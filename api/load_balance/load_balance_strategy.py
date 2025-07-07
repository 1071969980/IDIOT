from abc import ABC, abstractmethod
import random
import time
import requests
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from .service_instance import ServiceInstanceBase

class LoadBalanceStrategy(ABC):
    """负载均衡策略抽象基类"""
    @abstractmethod
    def select_instance(self, instances: List[ServiceInstanceBase]) -> ServiceInstanceBase:
        pass

class RandomStrategy(LoadBalanceStrategy):
    """随机选择策略"""
    def select_instance(self, instances: List[ServiceInstanceBase]) -> ServiceInstanceBase:
        return random.choice(instances)

class RoundRobinStrategy(LoadBalanceStrategy):
    """轮询选择策略"""
    def __init__(self):
        self._index = 0
    
    def select_instance(self, instances: List[ServiceInstanceBase]) -> ServiceInstanceBase:
        instance = instances[self._index]
        self._index += 1
        if self._index >= len(instances):
            self._index = 0
        return instance