"""
核心装饰器工厂模块

提供 lifecycle_hook 和 agent_decorator 装饰器工厂。
"""

import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Type

from .composer import MethodComposer
from .signature_validator import LifecycleSignatureValidator, SignatureMismatchError


class HookPosition(Enum):
    """钩子执行位置"""
    BEFORE = "before"
    AFTER = "after"


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
    position: HookPosition = HookPosition.AFTER  # 执行位置，默认为 after


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
    modifies_return: bool = False,
    position: str = "after"
) -> Callable[[Callable], Callable]:
    """
    创建生命周期钩子装饰器

    Args:
        method_name: 目标生命周期方法名
        modifies_return: 是否修改返回值
        position: 执行位置，"before" 或 "after"（默认 "after"）

    Returns:
        函数装饰器

    Example:
        @lifecycle_hook('on_generate_delta')
        async def log_delta(self, delta: str):
            print(f"Delta: {delta}")

        @lifecycle_hook('on_generate_delta', position='before')
        async def log_before(self, delta: str):
            print(f"Before: {delta}")
    """

    def decorator(func: Callable) -> Callable:
        # 转换为枚举
        position_enum = HookPosition(position)

        # 验证参数组合的合法性
        if modifies_return and position_enum == HookPosition.BEFORE:
            raise ValueError(
                "Invalid hook configuration: 'modifies_return=True' cannot be used with 'position=before'. "
                "Use 'position=after' when modifying return values."
            )

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
            modifies_return=modifies_return,
            position=position_enum
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
        # 将钩子分为 before 和 after 两个列表
        before_hooks = []
        after_hooks = []

        for hook_func in hooks:
            # 检查是否有元数据
            if not hasattr(hook_func, '_lifecycle_hook'):
                raise ValueError(
                    f"Function {hook_func.__name__} is not a lifecycle hook. "
                    f"Use @lifecycle_hook decorator first."
                )

            hook: LifecycleHook = hook_func._lifecycle_hook  # type: ignore
            if hook.position == HookPosition.BEFORE:
                before_hooks.append(hook)
            else:
                after_hooks.append(hook)

        # 先应用 before 钩子（reversed 以保持书写顺序）
        for hook in reversed(before_hooks):
            _apply_hook(cls, hook)

        # 再应用 after 钩子（按顺序）
        for hook in after_hooks:
            _apply_hook(cls, hook)

        return cls

    return class_decorator


def _apply_hook(cls: Type, hook: LifecycleHook) -> None:
    """应用单个钩子到类"""
    # 获取当前类中的方法
    if hasattr(cls, hook.method_name):
        current_method = getattr(cls, hook.method_name)
    else:
        AgentBase = _get_agent_base()
        current_method = getattr(AgentBase, hook.method_name)

    # 根据是否 async 和是否 modifies_return/position 选择组合方法
    is_async = inspect.iscoroutinefunction(current_method)

    if hook.position == HookPosition.BEFORE:
        # before 钩子：先执行钩子，再执行原方法
        if is_async:
            new_method = _composer.compose_async(current_method, hook.wrapper_func)
        else:
            new_method = _composer.compose_sync(current_method, hook.wrapper_func)
    else:  # AFTER
        # after 钩子：先执行原方法，再执行钩子
        if hook.modifies_return:
            # 修改返回值
            if is_async:
                new_method = _composer.compose_async_with_return(current_method, hook.wrapper_func)
            else:
                new_method = _composer.compose_sync_with_return(current_method, hook.wrapper_func)
        else:
            # 不修改返回值
            if is_async:
                new_method = _composer.compose_async_after_no_return(current_method, hook.wrapper_func)
            else:
                new_method = _composer.compose_sync_after_no_return(current_method, hook.wrapper_func)

    # 替换类方法
    setattr(cls, hook.method_name, new_method)
