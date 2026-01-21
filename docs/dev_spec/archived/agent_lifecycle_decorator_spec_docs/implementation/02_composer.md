---
文档标题：agent_lifecycle_decorator_spec_implementation_composer
文档描述：描述 composer.py 模块的实现，包括 MethodComposer 类和六种方法组合逻辑。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [composer.py](#composerpy)
    - [MethodComposer 类](#methodcomposer-类)
    - [关键代码片段](#关键代码片段)

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

## 相关文件

- [签名验证实现](./01_signature_validator.md)
- [装饰器工厂实现](./03_factory_and_init.md)
- [上下文文档](../agent_lifecycle_decorator_spec_context.md)
- [设计文档](../agent_lifecycle_decorator_spec_design.md)
