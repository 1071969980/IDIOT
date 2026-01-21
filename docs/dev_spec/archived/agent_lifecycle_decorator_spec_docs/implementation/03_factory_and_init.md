---
文档标题：agent_lifecycle_decorator_spec_implementation_factory
文档描述：描述 factory.py 模块和 __init__.py 的实现，包括 lifecycle_hook 装饰器工厂和 agent_decorator 类装饰器。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [factory.py](#factorypy)
    - [lifecycle_hook 装饰器工厂](#lifecycle_hook-装饰器工厂)
    - [agent_decorator 类装饰器](#agent_decorator-类装饰器)
    - [关键代码片段](#关键代码片段)
- [__init__.py](#__init__py)

---

## factory.py

### lifecycle_hook 装饰器工厂

**职责**：创建函数装饰器，验证签名并附加元数据。

**输入**：
- `method_name`：目标生命周期方法名
- `modifies_return`：是否修改返回值
- `position`：执行位置（`"before"` 或 `"after"`，默认 `"after"`）

**输出**：函数装饰器

### agent_decorator 类装饰器

**职责**：将钩子应用到类的生命周期方法上，分离 before/after 钩子并按正确顺序应用。

**输入**：
- `*hooks`：钩子函数列表

**输出**：类装饰器

### 关键代码片段

#### HookPosition 枚举和 LifecycleHook 数据类

```python
from dataclasses import dataclass
from enum import Enum
from typing import Callable

class HookPosition(Enum):
    """钩子执行位置"""
    BEFORE = "before"
    AFTER = "after"

@dataclass
class LifecycleHook:
    """生命周期钩子元数据"""
    method_name: str           # 目标方法名
    wrapper_func: Callable     # 钩子函数
    modifies_return: bool = False  # 是否修改返回值
    position: HookPosition = HookPosition.AFTER  # 执行位置，默认为 after
```

#### lifecycle_hook 装饰器工厂

```python
from typing import Callable
from .signature_validator import LifecycleSignatureValidator, SignatureMismatchError
from .composer import MethodComposer

# 全局验证器实例
_validator: LifecycleSignatureValidator | None = None

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
        func._lifecycle_hook = LifecycleHook(
            method_name=method_name,
            wrapper_func=func,
            modifies_return=modifies_return,
            position=position_enum
        )

        return func

    return decorator
```

#### agent_decorator 类装饰器

```python
import inspect
from typing import Callable, Type
from .composer import MethodComposer

_composer = MethodComposer()

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

            hook: LifecycleHook = hook_func._lifecycle_hook
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
```

---

## __init__.py

**职责**：导出公共 API。

```python
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

from .factory import HookPosition, lifecycle_hook, agent_decorator, LifecycleHook
from .signature_validator import SignatureMismatchError

__all__ = [
    # 核心装饰器
    'lifecycle_hook',
    'agent_decorator',
    # 枚举
    'HookPosition',
    # 异常
    'SignatureMismatchError',
    # 内部类型（高级用法）
    'LifecycleHook',
]
```

---

## 相关文件

- [签名验证实现](./01_signature_validator.md)
- [方法组合实现](./02_composer.md)
- [上下文文档](../agent_lifecycle_decorator_spec_context.md)
- [设计文档](../agent_lifecycle_decorator_spec_design.md)
