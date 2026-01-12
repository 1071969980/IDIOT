"""
核心装饰器工厂模块

提供 lifecycle_hook 和 agent_decorator 装饰器工厂。
"""

import inspect
from dataclasses import dataclass
from typing import Callable, Type

from .composer import MethodComposer
from .signature_validator import LifecycleSignatureValidator, SignatureMismatchError

# 延迟导入 AgentBase 以避免循环导入
def _get_agent_base():
    from api.agent.base_agent import AgentBase
    return AgentBase


@dataclass
class LifecycleHook:
    """生命周期钩子元数据"""
    method_name: str           # 目标方法名
    wrapper_func: Callable     # 钩子函数
    modifies_return: bool = False  # 是否修改返回值


# 全局验证器和组合器实例
_validator: LifecycleSignatureValidator | None = None
_composer = MethodComposer()


def _ensure_validator() -> LifecycleSignatureValidator:
    """确保验证器已初始化"""
    global _validator
    if _validator is None:
        _validator = LifecycleSignatureValidator(_get_agent_base())
    return _validator


def lifecycle_hook(
    method_name: str,
    *,
    modifies_return: bool = False
) -> Callable[[Callable], Callable]:
    """
    创建生命周期钩子装饰器

    Args:
        method_name: 目标生命周期方法名
        modifies_return: 是否修改返回值

    Returns:
        函数装饰器

    Example:
        @lifecycle_hook('on_generate_delta')
        async def log_delta(self, delta: str):
            print(f"Delta: {delta}")
    """

    def decorator(func: Callable) -> Callable:
        # 验证签名
        validator = _ensure_validator()
        try:
            validator.validate(method_name, func, modifies_return)
        except SignatureMismatchError as e:
            raise SignatureMismatchError(
                method_name,
                e.expected,
                e.provided
            ) from e

        # 附加元数据
        func._lifecycle_hook = LifecycleHook(  # type: ignore
            method_name=method_name,
            wrapper_func=func,
            modifies_return=modifies_return
        )

        return func

    return decorator


def agent_decorator(*hooks: Callable) -> Callable[[Type], Type]:
    """
    类装饰器，将生命周期钩子应用到 AgentBase 子类

    Args:
        *hooks: 由 @lifecycle_hook 创建的钩子函数

    Returns:
        类装饰器

    Example:
        @agent_decorator(log_delta, track_metrics)
        class MyAgent(AgentBase):
            pass
    """

    def class_decorator(cls: Type) -> Type:
        # 反转钩子列表以保持书写顺序执行
        # 每个钩子包装当前方法，后应用的钩子成为外层包装（先执行）
        # 反转后，第一个钩子最后应用（成为最外层），从而最先执行
        for hook_func in reversed(hooks):
            # 检查是否有元数据
            if not hasattr(hook_func, '_lifecycle_hook'):
                raise ValueError(
                    f"Function {hook_func.__name__} is not a lifecycle hook. "
                    f"Use @lifecycle_hook decorator first."
                )

            hook: LifecycleHook = hook_func._lifecycle_hook  # type: ignore

            # 获取当前类中的方法（可能是子类覆盖的，也可能是继承的）
            if hasattr(cls, hook.method_name):
                current_method = getattr(cls, hook.method_name)
            else:
                # 从 AgentBase 获取
                AgentBase = _get_agent_base()
                current_method = getattr(AgentBase, hook.method_name)

            # 根据是否 async 和是否修改返回值选择组合方法
            is_async = inspect.iscoroutinefunction(current_method)

            if hook.modifies_return:
                if is_async:
                    new_method = _composer.compose_async_with_return(
                        current_method, hook.wrapper_func
                    )
                else:
                    new_method = _composer.compose_sync_with_return(
                        current_method, hook.wrapper_func
                    )
            else:
                if is_async:
                    new_method = _composer.compose_async(
                        current_method, hook.wrapper_func
                    )
                else:
                    new_method = _composer.compose_sync(
                        current_method, hook.wrapper_func
                    )

            # 替换类方法
            setattr(cls, hook.method_name, new_method)

        return cls

    return class_decorator
