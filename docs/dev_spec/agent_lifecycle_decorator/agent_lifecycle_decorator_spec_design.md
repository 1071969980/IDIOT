---
文档标题：agent_lifecycle_decorator_spec_design
文档描述：描述 AgentBase 生命周期装饰器系统的需求、概念层面的设计结构和自然语言表达的执行逻辑。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [需求分析](#需求分析)
- [设计原则](#设计原则)
- [核心概念](#核心概念)
    - [生命周期钩子 (Lifecycle Hook)](#生命周期钩子-lifecycle-hook)
    - [装饰器工厂 (Decorator Factory)](#装饰器工厂-decorator-factory)
    - [方法组合 (Method Composition)](#方法组合-method-composition)
    - [签名验证 (Signature Validation)](#签名验证-signature-validation)
- [API 设计](#api-设计)
    - [lifecycle_hook 装饰器](#lifecycle_hook-装饰器)
    - [agent_decorator 装饰器](#agent_decorator-装饰器)
- [执行逻辑](#执行逻辑)
    - [定义时流程](#定义时流程)
    - [运行时流程](#运行时流程)
- [签名匹配规则](#签名匹配规则)

---

## 需求分析

### 核心需求

1. **灵活组合功能**：通过装饰器在类定义时动态添加生命周期方法功能，替代僵化的继承模式

2. **签名稳健验证**：从 AgentBase 反射获取方法签名，验证装饰器函数的正确性，防止运行时错误

3. **执行顺序可控**：多个装饰器按注册顺序（书写顺序）执行，简单直观

4. **零侵入现有代码**：无需修改现有 AgentBase 代码，新系统与现有代码共存

5. **支持返回值修改**：对于有返回值的生命周期方法，允许装饰器修改返回值

### 功能需求

| 需求 | 描述 | 优先级 |
|------|------|--------|
| 定义生命周期钩子 | 使用装饰器标记函数为生命周期钩子 | P0 |
| 验证函数签名 | 检查钩子函数与原方法签名是否匹配 | P0 |
| 组合方法实现 | 将钩子函数与原方法组合成新的方法 | P0 |
| 支持异步方法 | 正确处理 async 生命周期方法 | P0 |
| 支持同步方法 | 正确处理同步生命周期方法 | P0 |
| 修改返回值 | 允许钩子修改有返回值方法的返回值 | P0 |

### 非功能需求

| 需求 | 描述 |
|------|------|
| 类型安全 | 尽可能保持类型提示支持 |
| 性能 | 最小化运行时开销 |
| 可读性 | API 简洁直观，符合 Python 习惯 |
| 错误处理 | 提供清晰的错误信息 |

---

## 设计原则

### 1. 简化优先

移除复杂的优先级控制，执行顺序等于书写顺序，符合 Python 装饰器的直观认知：

```python
@agent_decorator(hook1, hook2, hook3)  # 执行顺序：hook1 → hook2 → hook3
class MyAgent(AgentBase):
    pass
```

### 2. 早期失败

签名验证在类定义时进行，而不是运行时，确保错误尽早被发现：

```python
@lifecycle_hook('on_generate_delta')
async def wrong_hook(self, wrong_param: int):  # 定义时就会报错
    pass
```

### 3. 零侵入

装饰器系统完全独立，不修改 AgentBase 的任何代码：

- 通过反射读取 AgentBase 方法签名
- 通过类装饰器替换子类方法
- 现有继承模式继续工作

### 4. 自包含

每个装饰器函数携带所需的全部元数据：

```python
@lifecycle_hook('on_generate_delta')
async def my_hook(self, delta: str):
    pass

# my_hook._lifecycle_hook 包含所有元数据
```

---

## 核心概念

### 生命周期钩子 (Lifecycle Hook)

**定义**：一个被 `@lifecycle_hook` 装饰的函数，它可以在特定生命周期事件发生时执行自定义逻辑。

**特性**：
- 携带元数据（目标方法名、是否修改返回值）
- 签名与目标生命周期方法匹配（或满足 modifies_return 规则）
- 可以是异步或同步函数

**示例**：
```python
@lifecycle_hook('on_generate_delta')
async def log_delta(self, delta: str):
    print(f"Delta: {delta}")
```

---

### 装饰器工厂 (Decorator Factory)

**定义**：一个返回装饰器的函数，用于创建和配置生命周期钩子。

**`lifecycle_hook` 工厂**：
- 接收目标方法名作为参数
- 返回一个函数装饰器
- 验证函数签名
- 在函数上附加元数据

**`agent_decorator` 工厂**：
- 接收多个钩子函数作为参数
- 返回一个类装饰器
- 将钩子应用到类的生命周期方法上

---

### 方法组合 (Method Composition)

**定义**：将多个函数（钩子和原方法）组合成一个新的函数，按顺序调用。

**组合策略**：

1. **不修改返回值** (`modifies_return=False`)：
   ```
   执行钩子 → 执行原方法 → 返回原方法的返回值
   ```

2. **修改返回值** (`modifies_return=True`)：
   ```
   执行原方法 → 将返回值传给钩子 → 返回钩子的返回值
   ```

**链式组合**（多个钩子）：
```
钩子1 → 钩子2 → ... → 钩子N → 原方法
```

---

### 签名验证 (Signature Validation)

**定义**：使用 Python 的 `inspect` 模块从 AgentBase 反射获取方法签名，验证钩子函数是否匹配。

**验证维度**：
1. **参数个数**：钩子参数个数是否与原方法匹配
2. **异步/同步**：钩子是否是 async/sync 与原方法一致
3. **返回值参数**：`modifies_return=True` 时，验证钩子多一个参数

**验证时机**：类定义时（应用 `@lifecycle_hook` 装饰器时）

---

## API 设计

### `lifecycle_hook` 装饰器

**签名**：
```python
def lifecycle_hook(
    method_name: str,
    *,
    modifies_return: bool = False
) -> Callable[[Callable], Callable]:
    ...
```

**参数**：
- `method_name`：目标生命周期方法名（如 `'on_generate_delta'`）
- `modifies_return`：是否修改返回值，默认 `False`

**返回**：函数装饰器

**使用示例**：

```python
# 基本用法
@lifecycle_hook('on_generate_delta')
async def log_delta(self, delta: str):
    print(f"Delta: {delta}")

# 修改返回值
@lifecycle_hook('prepare_kwargs', modifies_return=True)
async def add_temperature(self, base_kwargs: dict, thinking: bool) -> dict:
    base_kwargs['temperature'] = 0.7
    return base_kwargs
```

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
       ├─> 反转钩子列表（hookN, ..., hook2, hook1）
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

```
调用 agent.on_generate_delta(delta)
        │
        ▼
┌─────────────────────────────────┐
│ 组合方法的执行流程：              │
│                                  │
│ 1. log_delta(agent, delta)       │
│    └─> 执行日志逻辑              │
│                                  │
│ 2. 原始方法(agent, delta)        │
│    └─> 执行原始逻辑              │
│                                  │
│ 3. 返回结果                      │
└─────────────────────────────────┘
```

**对于 `modifies_return=True` 的情况**：

```
调用 agent.prepare_kwargs(thinking)
        │
        ▼
┌─────────────────────────────────┐
│ 1. 原始方法(agent, thinking)     │
│    └─> 返回 base_kwargs          │
│                                  │
│ 2. add_temperature(agent,       │
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

- [上下文文档](./agent_lifecycle_decorator_spec_context.md)
- [实现文档](./agent_lifecycle_decorator_spec_implementation.md)
- [审核文档](./agent_lifecycle_decorator_spec_review.md)
