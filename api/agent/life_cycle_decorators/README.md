# Agent Lifecycle Decorators

基于装饰器的 Agent 生命周期钩子系统，提供灵活的生命周期方法扩展机制，替代僵化的继承模式。

## 设计理念

传统的生命周期扩展通常需要重写父类方法，这种方式存在以下问题：
- 破坏了原有的继承链
- 需要手动调用 `super()` 方法
- 难以组合多个扩展行为
- 代码耦合度高

本组件采用**装饰器模式**来解决这些问题：
- 保持继承链完整
- 自动处理方法组合
- 支持多个钩子的组合使用
- 钩子之间相互独立

## 模块结构

```
life_cycle_decorators/
├── __init__.py              # 模块入口，导出核心 API
├── factory.py               # 核心装饰器工厂
├── composer.py              # 方法组合器
└── signature_validator.py   # 签名验证器
```

### 模块职责

| 模块 | 职责 |
|------|------|
| `factory.py` | 提供 `lifecycle_hook` 和 `agent_decorator` 装饰器，定义钩子元数据 |
| `composer.py` | 将钩子函数与原方法按不同策略组合成新方法 |
| `signature_validator.py` | 验证钩子函数签名与目标生命周期方法是否匹配 |

## 快速开始

### 1. 定义钩子

使用 `@lifecycle_hook` 装饰器定义钩子：

```python
from api.agent.life_cycle_decorators import lifecycle_hook, agent_decorator

# 在方法执行后添加钩子
@lifecycle_hook('on_generate_delta')
async def log_delta(self, delta: str):
    print(f"Delta: {delta}")

# 在方法执行前添加钩子
@lifecycle_hook('on_agent_start', position='before')
async def log_agent_start(self, user_message: str):
    print(f"Agent starting with: {user_message}")

# 修改返回值的钩子
@lifecycle_hook('on_generate_complete', modifies_return=True)
async def sanitize_output(self, result: str, user_message: str) -> str:
    return result.strip()
```

### 2. 应用钩子

使用 `@agent_decorator` 将钩子应用到 Agent 类：

```python
@agent_decorator(log_delta, log_agent_start, sanitize_output)
class MyAgent(AgentBase):
    pass
```

## 钩子执行顺序

当多个钩子应用于同一方法时，执行顺序如下：

```
before 钩子（按书写顺序）→ 原方法 → after 钩子（按书写顺序）
```

示例：

```python
@lifecycle_hook('on_agent_start', position='before')
async def before_1(self, user_message: str):
    print("Before 1")

@lifecycle_hook('on_agent_start', position='before')
async def before_2(self, user_message: str):
    print("Before 2")

@lifecycle_hook('on_agent_start', position='after')
async def after_1(self, user_message: str):
    print("After 1")

@lifecycle_hook('on_agent_start', position='after')
async def after_2(self, user_message: str):
    print("After 2")

@agent_decorator(before_1, before_2, after_1, after_2)
class MyAgent(AgentBase):
    pass

# 执行顺序输出：
# Before 1
# Before 2
# [原方法执行]
# After 1
# After 2
```

## 可用的生命周期方法

本装饰器系统支持 `AgentBase` 中定义的所有生命周期方法。

要查看完整的方法列表和详细说明，请参考 `api/agent/base_agent.py` 中的 `AgentBase` 类实现。

**查看时请注意以下几点：**

1. **方法签名**：钩子函数的参数列表必须与目标生命周期方法完全匹配（除了 `modifies_return=True` 的情况）
2. **异步/同步性质**：异步生命周期方法只能用异步钩子，同步方法只能用同步钩子
3. **返回值类型**：如果使用 `modifies_return=True`，钩子的返回值类型应与原方法一致
4. **参数类型**：注意参数的类型注解，这有助于 `LifecycleSignatureValidator` 在定义时进行验证

## API 参考

### `lifecycle_hook(method_name, *, modifies_return=False, position="after")`

创建生命周期钩子装饰器。

**参数：**
- `method_name` (`str`): 目标生命周期方法名
- `modifies_return` (`bool`): 是否修改返回值，默认 `False`
- `position` (`str`): 执行位置，`"before"` 或 `"after"`（默认 `"after"`）

**注意：** `modifies_return=True` 不能与 `position="before"` 同时使用。

### `agent_decorator(*hooks)`

类装饰器，将生命周期钩子应用到 `AgentBase` 子类。

**参数：**
- `*hooks`: 由 `@lifecycle_hook` 创建的钩子函数

### `HookPosition`

枚举类型，定义钩子执行位置：
- `HookPosition.BEFORE`: 在原方法前执行
- `HookPosition.AFTER`: 在原方法后执行

### 异常

#### `SignatureMismatchError`

钩子函数签名与生命周期方法不匹配时抛出。

```python
@lifecycle_hook('on_generate_delta')
async def bad_hook(self, wrong_param: int):  # 签名不匹配
    pass
# SignatureMismatchError: Signature mismatch for 'on_generate_delta':
#   Expected: (delta: str) -> None
#   Provided: (wrong_param: int) -> None
```

## 方法组合策略

`MethodComposer` 类提供了多种方法组合策略，由框架根据钩子配置自动选择：

| 策略 | 执行顺序 | 返回值 | 使用场景 |
|------|----------|--------|----------|
| `compose_async` | wrapper → base | base 返回值 | before 钩子（异步） |
| `compose_sync` | wrapper → base | base 返回值 | before 钩子（同步） |
| `compose_async_with_return` | base → wrapper | wrapper 返回值 | modifies_return=True（异步） |
| `compose_sync_with_return` | base → wrapper | wrapper 返回值 | modifies_return=True（同步） |
| `compose_async_after_no_return` | base → wrapper | base 返回值 | after 钩子，不修改返回值（异步） |
| `compose_sync_after_no_return` | base → wrapper | base 返回值 | after 钩子，不修改返回值（同步） |

## 签名验证规则

`LifecycleSignatureValidator` 在钩子定义时验证签名：

1. **参数个数匹配**：钩子参数必须与目标方法一致
2. **参数类型匹配**：参数种类（POSITIONAL、KEYWORD_ONLY 等）必须一致
3. **异步/同步匹配**：钩子必须与目标方法的异步/同步性质一致
4. **修改返回值规则**：`modifies_return=True` 时，钩子第一个参数接收返回值

```python
# 正确：参数匹配
@lifecycle_hook('on_generate_delta')
async def log_delta(self, delta: str):
    print(delta)

# 正确：修改返回值
@lifecycle_hook('on_generate_complete', modifies_return=True)
async def modify_result(self, result: str, user_message: str) -> str:
    return result + " [modified]"

# 错误：参数不匹配
@lifecycle_hook('on_generate_delta')
async def wrong_signature(self, wrong: int):  # 类型错误
    pass
```

## 高级用法

### 可复用的钩子库

```python
# hooks.py
@lifecycle_hook('on_agent_start', position='before')
async def log_start(self, user_message: str):
    print(f"Starting: {user_message}")

@lifecycle_hook('on_generate_delta')
async def log_delta(self, delta: str):
    print(f"Delta: {delta}")

@lifecycle_hook('on_tool_call_error')
async def log_tool_error(self, error: Exception, tool_name: str, tool_args: dict):
    print(f"Tool {tool_name} failed: {error}")
```

```python
# my_agent.py
from hooks import log_start, log_delta, log_tool_error

@agent_decorator(log_start, log_delta, log_tool_error)
class MyAgent(AgentBase):
    pass
```

### 条件钩子

```python
DEBUG = True

@lifecycle_hook('on_generate_delta')
async def debug_delta(self, delta: str):
    if DEBUG:
        print(f"DEBUG: {delta}")
```

### 钩子链中共享状态

```python
@dataclass
class HookState:
    metrics: dict = field(default_factory=dict)

@lifecycle_hook('on_agent_start', position='before')
async def init_metrics(self, user_message: str):
    self._hook_state = HookState()

@lifecycle_hook('on_tool_call_complete')
async def track_tool(self, result: Any, tool_name: str, tool_args: dict):
    self._hook_state.metrics[tool_name] = self._hook_state.metrics.get(tool_name, 0) + 1
```
