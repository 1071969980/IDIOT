---
文档标题：agent_lifecycle_decorator_spec_implementation
文档描述：从软件工程的角度描述 AgentBase 生命周期装饰器系统的实现，包括文件夹结构、每个文件中的关键代码片段示例等。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [文件结构](#文件结构)
- [signature_validator.py](#signature_validatorpy)
    - [LifecycleSignatureValidator 类](#lifecyclesignaturevalidator-类)
    - [关键代码片段](#关键代码片段)
- [composer.py](#composerpy)
    - [MethodComposer 类](#methodcomposer-类)
    - [关键代码片段](#关键代码片段-1)
- [factory.py](#factorypy)
    - [lifecycle_hook 装饰器工厂](#lifecycle_hook-装饰器工厂)
    - [agent_decorator 类装饰器](#agent_decorator-类装饰器)
    - [关键代码片段](#关键代码片段-2)
- [__init__.py](#__init__py)

---

## 文件结构

```
api/agent/
├── base_agent.py                    # 现有文件 - 无需修改
└── life_cycle_decorators/           # 新建目录
    ├── __init__.py                  # 公共 API 导出
    ├── factory.py                   # 核心装饰器工厂
    ├── signature_validator.py       # 签名验证
    └── composer.py                  # 方法组合逻辑
```

---

## signature_validator.py

### LifecycleSignatureValidator 类

**职责**：从 AgentBase 反射获取方法签名，验证钩子函数签名是否匹配。

**核心方法**：
- `__init__(base_class)`：初始化，提取所有生命周期方法签名
- `_extract_signatures()`：反射获取 AgentBase 方法签名
- `validate(method_name, func, modifies_return)`：验证钩子函数签名

### 关键代码片段

#### 签名提取

```python
import inspect
from typing import Any, Callable, Type

class LifecycleSignatureValidator:
    """验证生命周期钩子函数签名"""

    def __init__(self, base_class: Type):
        self.base_class = base_class
        self._signatures = self._extract_signatures()

    def _extract_signatures(self) -> dict[str, inspect.Signature]:
        """从 AgentBase 提取所有生命周期方法签名"""
        signatures = {}

        # 异步生命周期方法列表
        async_methods = [
            'on_agent_start', 'on_iteration_start', 'on_iteration_end',
            'on_generate_start', 'on_generate_delta', 'on_generate_complete',
            'on_tool_calls_start_batch', 'on_tool_calls_complete_batch',
            'on_tool_call_start', 'on_tool_call_complete', 'on_tool_call_error',
            'on_agent_complete', 'on_agent_cancel',
            'prepare_kwargs', 'prepare_tools',
        ]

        # 同步生命周期方法列表
        sync_methods = [
            'loop_flag_init', 'loop_flag_unset_on_iter_start',
            'loop_flag_set_on_tool_calls', 'loop_flag_should_continue',
        ]

        for method_name in async_methods + sync_methods:
            if hasattr(self.base_class, method_name):
                method = getattr(self.base_class, method_name)
                signatures[method_name] = inspect.signature(method)

        return signatures
```

#### 签名验证

```python
    def validate(self, method_name: str, func: Callable, modifies_return: bool = False) -> None:
        """
        验证钩子函数签名是否匹配目标生命周期方法

        Args:
            method_name: 目标生命周期方法名
            func: 钩子函数
            modifies_return: 是否修改返回值

        Raises:
            ValueError: 未知的方法名
            SignatureMismatchError: 签名不匹配
        """
        if method_name not in self._signatures:
            raise ValueError(f"Unknown lifecycle method: '{method_name}'")

        expected_sig = self._signatures[method_name]
        provided_sig = inspect.signature(func)

        # 获取参数列表（排除 self）
        expected_params = [
            p for p in expected_sig.parameters.values()
            if p.name != 'self'
        ]
        provided_params = [
            p for p in provided_sig.parameters.values()
            if p.name not in ('self', 'agent', 'instance')
        ]

        # 检查参数个数
        if modifies_return:
            # modifies_return=True 时，钩子应该比原方法多一个参数
            expected_count = len(expected_params) + 1
            if len(provided_params) != expected_count:
                raise SignatureMismatchError(
                    method_name,
                    f"Expected {expected_count} parameters (1 for return value + {len(expected_params)} for original parameters)",
                    f"Got {len(provided_params)} parameters"
                )
            # 验证第2个参数之后的参数是否匹配
            for orig, prov in zip(expected_params, provided_params[1:]):
                if orig.kind != prov.kind:
                    raise SignatureMismatchError(
                        method_name,
                        f"Parameter kind mismatch at position {list(expected_params).index(orig) + 1}",
                        f"Expected {orig.kind}, got {prov.kind}"
                    )
        else:
            # modifies_return=False 时，钩子参数应该与原方法完全匹配
            if len(provided_params) != len(expected_params):
                raise SignatureMismatchError(
                    method_name,
                    f"Expected {len(expected_params)} parameters",
                    f"Got {len(provided_params)} parameters"
                )
            for orig, prov in zip(expected_params, provided_params):
                if orig.kind != prov.kind:
                    raise SignatureMismatchError(
                        method_name,
                        f"Parameter kind mismatch at position {list(expected_params).index(orig)}",
                        f"Expected {orig.kind}, got {prov.kind}"
                    )

        # 检查异步/同步是否匹配
        expected_is_async = inspect.iscoroutinefunction(
            getattr(self.base_class, method_name)
        )
        provided_is_async = inspect.iscoroutinefunction(func)

        if expected_is_async != provided_is_async:
            raise SignatureMismatchError(
                method_name,
                "async function" if expected_is_async else "sync function",
                "async function" if provided_is_async else "sync function"
            )
```

#### 异常定义

```python
class SignatureMismatchError(Exception):
    """钩子函数签名与生命周期方法不匹配"""

    def __init__(self, method_name: str, expected: str, provided: str):
        self.method_name = method_name
        self.expected = expected
        self.provided = provided
        super().__init__(
            f"Signature mismatch for '{method_name}':\n"
            f"  Expected: {expected}\n"
            f"  Provided: {provided}"
        )
```

---

## composer.py

### MethodComposer 类

**职责**：将多个函数（钩子和原方法）组合成一个新的函数。

**核心方法**：
- `compose_async(base_method, wrapper)`：组合异步方法（before，不修改返回值）
- `compose_async_with_return(base_method, wrapper)`：组合异步方法（after，修改返回值）
- `compose_async_after_no_return(base_method, wrapper)`：组合异步方法（after，不修改返回值）
- `compose_sync(base_method, wrapper)`：组合同步方法（before，不修改返回值）
- `compose_sync_with_return(base_method, wrapper)`：组合同步方法（after，修改返回值）
- `compose_sync_after_no_return(base_method, wrapper)`：组合同步方法（after，不修改返回值）

### 关键代码片段

#### 异步方法组合（before，不修改返回值）

```python
import functools
from typing import Callable, Any

class MethodComposer:
    """组合生命周期方法实现"""

    @staticmethod
    def compose_async(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合异步方法，先执行 wrapper，再执行 base_method

        执行顺序：wrapper → base_method
        返回值：base_method 的返回值
        """
        @functools.wraps(base_method)
        async def composed(self, *args, **kwargs):
            # 先执行钩子
            await wrapper(self, *args, **kwargs)
            # 再执行原方法
            result = await base_method(self, *args, **kwargs)
            return result

        return composed
```

#### 异步方法组合（after，修改返回值）

```python
    @staticmethod
    def compose_async_with_return(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合异步方法，将 base_method 的返回值传递给 wrapper

        执行顺序：base_method → wrapper（接收返回值）
        返回值：wrapper 的返回值
        """
        @functools.wraps(base_method)
        async def composed(self, *args, **kwargs):
            # 先执行原方法
            base_result = await base_method(self, *args, **kwargs)
            # 将返回值传给钩子
            result = await wrapper(self, base_result, *args, **kwargs)
            return result

        return composed
```

#### 异步方法组合（after，不修改返回值）

```python
    @staticmethod
    def compose_async_after_no_return(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合异步方法，先执行 base_method，再执行 wrapper，不修改返回值

        执行顺序：base_method → wrapper
        返回值：base_method 的返回值
        """
        @functools.wraps(base_method)
        async def composed(self, *args, **kwargs):
            # 先执行原方法
            result = await base_method(self, *args, **kwargs)
            # 再执行钩子
            await wrapper(self, *args, **kwargs)
            # 返回原方法的返回值
            return result

        return composed
```

#### 同步方法组合（before，不修改返回值）

```python
    @staticmethod
    def compose_sync(base_method: Callable, wrapper: Callable) -> Callable:
        """组合同步方法（不修改返回值）"""
        @functools.wraps(base_method)
        def composed(self, *args, **kwargs):
            wrapper(self, *args, **kwargs)
            result = base_method(self, *args, **kwargs)
            return result

        return composed
```

#### 同步方法组合（after，修改返回值）

```python
    @staticmethod
    def compose_sync_with_return(base_method: Callable, wrapper: Callable) -> Callable:
        """组合同步方法（修改返回值）"""
        @functools.wraps(base_method)
        def composed(self, *args, **kwargs):
            base_result = base_method(self, *args, **kwargs)
            result = wrapper(self, base_result, *args, **kwargs)
            return result

        return composed
```

#### 同步方法组合（after，不修改返回值）

```python
    @staticmethod
    def compose_sync_after_no_return(base_method: Callable, wrapper: Callable) -> Callable:
        """
        组合同步方法，先执行 base_method，再执行 wrapper，不修改返回值

        执行顺序：base_method → wrapper
        返回值：base_method 的返回值
        """
        @functools.wraps(base_method)
        def composed(self, *args, **kwargs):
            # 先执行原方法
            result = base_method(self, *args, **kwargs)
            # 再执行钩子
            wrapper(self, *args, **kwargs)
            # 返回原方法的返回值
            return result

        return composed
```

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
```

---

## 相关文件

- [上下文文档](./agent_lifecycle_decorator_spec_context.md)
- [设计文档](./agent_lifecycle_decorator_spec_design.md)
- [审核文档](./agent_lifecycle_decorator_spec_review.md)
- [AgentBase 实现](../../../../api/agent/base_agent.py)
