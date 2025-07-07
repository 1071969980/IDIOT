from math import sqrt
import time
from collections.abc import Callable
from typing import Any, Awaitable

import asyncio
from .exception import (
    MaxRetriesExceededError,
    NoAvailableInstanceError,
    RequestTimeoutError,
    LimitExceededError,
    ServiceError,
)
from .load_balance_strategy import LoadBalanceStrategy, RoundRobinStrategy
from .service_instance import ServiceInstanceBase
from .service_regeistry import ServiceConfig, ServiceRegistry

from typing import Generic, TypeVar

T = TypeVar("T")

class LoadBalancer:
    """负载均衡核心控制器"""

    def __init__(
        self,
        registry: ServiceRegistry,
        strategy_type: type[LoadBalanceStrategy] = RoundRobinStrategy,
    ):
        self.registry = registry
        self.strategy_type = strategy_type
    async def execute(
        self,
        service_name: str,
        request_func: Callable[[ServiceInstanceBase], Awaitable[T]],
        override_config: ServiceConfig | None = None,
    ) -> T:
        """
        执行负载均衡请求
        :param service_name: 注册的服务名称
        :param request_func: 实际请求的函数 (接受ServiceInstance参数)
        :param override_config: 可覆盖的配置
        :return: 请求结果
        """
        instances = self.registry.get_instances(service_name)
        if not instances:
            msg = f"No instances for {service_name}"
            raise NoAvailableInstanceError(msg)

        config = override_config or self.registry.get_config(service_name)
        strategy = self.strategy_type()

        last_exception = None
        for attempt in range(config.max_retries + 1):
            instance = strategy.select_instance(instances)
            try:
                return await request_func(instance)
            except (RequestTimeoutError, ServiceError, LimitExceededError) as e:
                last_exception = e
                if attempt < config.max_retries:
                    delay = config.retry_delay * (config.retry_backoff**sqrt(attempt))
                    asyncio.sleep(delay)
            except Exception:
                raise

        msg = f"Max retries exceeded for {service_name}"
        raise MaxRetriesExceededError(msg) from last_exception