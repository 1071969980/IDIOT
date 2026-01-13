---
文档标题：agent_lifecycle_decorator_spec_implementation_validator
文档描述：描述 signature_validator.py 模块的实现，包括 LifecycleSignatureValidator 类和签名验证逻辑。
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

---

## 文件结构

```
api/agent/
└── life_cycle_decorators/
    ├── __init__.py
    ├── factory.py
    ├── signature_validator.py      # 本文档描述
    └── composer.py
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
            'on_agent_complete', 'on_agent_cancel', 'on_create_assistant_memory',
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

## 相关文件

- [方法组合实现](./02_composer.md)
- [装饰器工厂实现](./03_factory_and_init.md)
- [上下文文档](../agent_lifecycle_decorator_spec_context.md)
- [设计文档](../agent_lifecycle_decorator_spec_design.md)
