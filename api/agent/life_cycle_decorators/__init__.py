"""
AgentBase 生命周期装饰器系统

提供基于装饰器的生命周期方法扩展功能，替代僵化的继承模式。

Example:
    from api.agent.life_cycle_decorators import lifecycle_hook, agent_decorator

    # 定义钩子
    @lifecycle_hook('on_generate_delta')
    async def log_delta(self, delta: str):
        print(f"Delta: {delta}")

    # 应用到 agent 类
    @agent_decorator(log_delta)
    class MyAgent(AgentBase):
        pass
"""

from .factory import lifecycle_hook, agent_decorator, LifecycleHook
from .signature_validator import SignatureMismatchError

__all__ = [
    # 核心装饰器
    'lifecycle_hook',
    'agent_decorator',
    # 异常
    'SignatureMismatchError',
    # 内部类型（高级用法）
    'LifecycleHook',
]
