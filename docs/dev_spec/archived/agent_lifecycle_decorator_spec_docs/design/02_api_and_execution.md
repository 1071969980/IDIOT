---
文档标题：agent_lifecycle_decorator_spec_design_api
文档描述：描述 AgentBase 生命周期装饰器系统的 API 设计、执行逻辑和签名匹配规则。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [API 设计](#api-设计)
- [执行逻辑](#执行逻辑)
- [签名匹配规则](#签名匹配规则)

---

## API 设计

### `lifecycle_hook` 装饰器

**签名**：
```python
def lifecycle_hook(
    method_name: str,
    *,
    modifies_return: bool = False,
    position: str = "after"
) -> Callable[[Callable], Callable]:
    ...
```

**参数**：
- `method_name`：目标生命周期方法名（如 `'on_generate_delta'`）
- `modifies_return`：是否修改返回值，默认 `False`
- `position`：执行位置，`"before"` 或 `"after"`（默认 `"after"`）

**返回**：函数装饰器

**使用示例**：

```python
# 基本用法（默认在原函数之后执行）
@lifecycle_hook('on_generate_delta')
async def log_delta(self, delta: str):
    print(f"Delta: {delta}")

# 在原函数之前执行
@lifecycle_hook('on_generate_delta', position='before')
async def log_before(self, delta: str):
    print(f"Before: {delta}")

# 修改返回值（必须配合 position='after'）
@lifecycle_hook('prepare_kwargs', modifies_return=True)
async def add_temperature(self, base_kwargs: dict, thinking: bool) -> dict:
    base_kwargs['temperature'] = 0.7
    return base_kwargs
```

**参数组合规则**：

| `modifies_return` | `position` | 说明 |
|------------------|------------|------|
| `False` | `"before"` | 在原函数之前执行 |
| `False` | `"after"` | 在原函数之后执行 |
| `True` | `"before"` | **不支持**（会抛出 `ValueError`） |
| `True` | `"after"` | 在原函数之后执行，可修改返回值 |

---

### `agent_decorator` 装饰器

**签名**：
```python
def agent_decorator(*hooks: Callable) -> Callable[[Type[AgentBase]], Type[AgentBase]]:
    ...
```

**参数**：
- `*hooks`：由 `@lifecycle_hook` 创建的钩子函数

**返回**：类装饰器

**使用示例**：

```python
# 单个钩子
@agent_decorator(log_delta)
class MyAgent(AgentBase):
    pass

# 多个钩子（按顺序执行）
@agent_decorator(init_config, log_delta, track_metrics)
class MyAgent(AgentBase):
    pass
```

---

## 执行逻辑

### 定义时流程

当 Python 解释器执行类定义时：

```
1. 定义钩子函数
   └─> @lifecycle_hook('method_name')
       ├─> 验证函数签名
       ├─> 创建 LifecycleHook 元数据
       └─> 附加到函数的 _lifecycle_hook 属性

2. 定义类
   └─> @agent_decorator(hook1, hook2, ...)
       ├─> 将钩子分为 before 和 after 两个列表
       ├─> before 钩子列表：反转后应用（保持书写顺序执行）
       ├─> after 钩子列表：按顺序应用
       ├─> 读取每个钩子的 _lifecycle_hook 属性
       ├─> 获取类中现有的生命周期方法
       ├─> 使用 MethodComposer 组合方法
       └─> 替换类中的生命周期方法
```

**时序图**：

```
@lifecycle_hook('on_generate_delta')        @agent_decorator(log_delta)
        │                                          │
        ▼                                          ▼
┌───────────────┐                        ┌───────────────┐
│ 验证签名       │                        │ 读取钩子元数据 │
│ 附加元数据     │                        │                │
└───────────────┘                        │ 获取原方法     │
        │                                  │                │
        │                                  │ 组合方法       │
        │                                  │                │
        │                                  │ 替换类方法     │
        │                                  └───────────────┘
        ▼                                          │
┌───────────────┐                                  │
│ log_delta 函数 │◄─────────────────────────────────┘
│ (带元数据)     │
└───────────────┘
```

---

### 运行时流程

当 Agent 运行并调用生命周期方法时：

#### 对于 `position='before'` 的钩子

```
调用 agent.on_generate_delta(delta)
        │
        ▼
┌─────────────────────────────────┐
│ 组合方法的执行流程：              │
│                                  │
│ 1. before_hook(agent, delta)     │
│    └─> 执行前置逻辑              │
│                                  │
│ 2. 原始方法(agent, delta)        │
│    └─> 执行原始逻辑              │
│                                  │
│ 3. 返回结果                      │
└─────────────────────────────────┘
```

#### 对于 `position='after'` 的钩子

```
调用 agent.on_generate_delta(delta)
        │
        ▼
┌─────────────────────────────────┐
│ 组合方法的执行流程：              │
│                                  │
│ 1. 原始方法(agent, delta)        │
│    └─> 执行原始逻辑              │
│                                  │
│ 2. after_hook(agent, delta)      │
│    └─> 执行后置逻辑              │
│                                  │
│ 3. 返回结果                      │
└─────────────────────────────────┘
```

#### 对于混合 before/after 钩子

```
调用 agent.on_generate_delta(delta)
        │
        ▼
┌─────────────────────────────────┐
│ 执行顺序：                       │
│                                  │
│ 1. before_hook1(agent, delta)    │
│ 2. before_hook2(agent, delta)    │
│ 3. 原始方法(agent, delta)        │
│ 4. after_hook1(agent, delta)     │
│ 5. after_hook2(agent, delta)     │
│                                  │
│ 6. 返回结果                      │
└─────────────────────────────────┘
```

**对于 `modifies_return=True` 的情况**（必须配合 `position='after'`）：

```
调用 agent.prepare_kwargs(thinking)
        │
        ▼
┌─────────────────────────────────┐
│ 1. 原始方法(agent, thinking)     │
│    └─> 返回 base_kwargs          │
│                                  │
│ 2. modify_hook(agent,            │
│       base_kwargs, thinking)     │
│    └─> 修改并返回 kwargs         │
│                                  │
│ 3. 返回修改后的 kwargs           │
└─────────────────────────────────┘
```

---

## 签名匹配规则

### `modifies_return=False`

钩子函数签名必须与原方法完全匹配（除了 `self` 参数）：

| 原方法签名 | 钩子签名 | 是否匹配 |
|------------|----------|----------|
| `method(self, p1: str)` | `hook(self, p1: str)` | ✓ |
| `method(self, p1: str)` | `hook(self, p1: int)` | ✓（类型不强制检查） |
| `method(self, p1: str)` | `hook(self, p1: str, p2: int)` | ✗（参数多了） |
| `method(self, p1: str)` | `hook(self, p1: str) -> None` | ✓ |
| `async def method(self, p1)` | `def hook(self, p1)` | ✗（async 不匹配） |

### `modifies_return=True`

钩子函数第一个参数接收原方法返回值，后续参数与原方法匹配：

| 原方法签名 | 钩子签名 | 是否匹配 |
|------------|----------|----------|
| `method(self, p1: str) -> dict` | `hook(self, ret: dict, p1: str) -> dict` | ✓ |
| `method(self, p1: str) -> dict` | `hook(self, result: dict, p1: str)` | ✓ |
| `method(self, p1: str) -> dict` | `hook(self, p1: str) -> dict` | ✗（少了返回值参数） |
| `method(self, p1: str) -> dict` | `hook(self, ret: dict, p1: str, p2: int)` | ✗（参数多了） |

### 参数名称

参数名称不强制检查，只检查参数个数和位置：

```python
# 以下都是合法的
@lifecycle_hook('on_generate_delta')
async def hook1(self, delta: str):  # 参数名与原方法相同
    pass

@lifecycle_hook('on_generate_delta')
async def hook2(self, content: str):  # 参数名不同
    pass
```

### 异步/同步检查

钩子的异步/同步性质必须与原方法一致：

```python
# 原方法是 async
async def on_generate_delta(self, delta: str): ...

# 钩子也必须是 async
@lifecycle_hook('on_generate_delta')
async def hook(self, delta: str):  # ✓
    pass

@lifecycle_hook('on_generate_delta')
def hook(self, delta: str):  # ✗
    pass
```

---

## 相关文件

- [需求分析与核心概念](./01_concepts.md)
- [上下文文档](../agent_lifecycle_decorator_spec_context.md)
- [实现文档](../agent_lifecycle_decorator_spec_implementation.md)
