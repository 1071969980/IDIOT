---
文档标题：agent_lifecycle_decorator_spec_context
文档描述：描述 AgentBase 生命周期装饰器系统的开发上下文，包括现有 AgentBase 类的架构、生命周期方法、以及当前继承模式的局限性。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [项目背景](#项目背景)
- [AgentBase 类架构](#agentbase-类架构)
- [生命周期方法详解](#生命周期方法详解)
    - [异步生命周期方法](#异步生命周期方法)
    - [同步生命周期方法](#同步生命周期方法)
- [当前继承模式及其局限性](#当前继承模式及其局限性)
- [相关代码基础设施](#相关代码基础设施)

---

## 项目背景

IDIOT (Intelligent Development Integrated & Operations Toolkit) 项目中，`AgentBase` 类是所有 Agent 策略的基础类，定义了 Agent 的核心执行循环和生命周期方法。当前系统采用继承模式来实现具体的 Agent 策略，子类通过覆盖生命周期方法来自定义行为。

然而，继承模式存在以下局限性：
- 代码重用困难：多个 Agent 共享相同功能时需要多层继承
- 功能组合僵化：难以灵活组合不同的功能模块
- 代码维护复杂：继承层次加深导致理解和维护困难

为解决这些问题，本开发任务旨在设计一个基于装饰器的生命周期方法扩展系统。

---

## AgentBase 类架构

`AgentBase` 是一个抽象基类，位于 `api/agent/base_agent.py`，其核心架构包括：

### 核心职责

1. **Agent 执行循环管理**：控制 Agent 的运行流程
2. **生命周期钩子**：在关键执行点提供可覆盖的方法
3. **工具调用管理**：处理 LLM 工具调用的执行
4. **记忆管理**：维护对话历史和 Agent 状态

### 类结构

```python
class AgentBase(ABC):
    def __init__(
        self,
        cancel_event: Event,
        tools: list[ChatCompletionToolParam],
        tool_call_function: dict[str, ToolClosure],
        loop_control: Any = None,
    ):
        # 初始化参数和内部状态
        ...
```

### 执行流程概览

```
on_agent_start()
    ↓
[准备 kwargs 和 tools]
    ↓
while loop_flag_should_continue():
    on_iteration_start()
        ↓
    on_generate_start()
        ↓
    [LLM 流式生成]
        ↓
    on_generate_delta() [每个 chunk]
        ↓
    on_generate_complete()
        ↓
    [如果需要工具调用]
        ↓
    on_tool_calls_start_batch()
        ↓
    on_tool_call_start() [每个工具]
        ↓
    [执行工具调用]
        ↓
    on_tool_call_complete() / on_tool_call_error()
        ↓
    on_tool_calls_complete_batch()
        ↓
    on_iteration_end()
    ↓
on_agent_complete() / on_agent_cancel()
```

---

## 生命周期方法详解

### 异步生命周期方法

AgentBase 定义了以下异步生命周期方法（按执行顺序排列）：

#### 1. `on_agent_start(memories)`
```python
async def on_agent_start(self, memories: list[ChatCompletionMessageParam]) -> None:
    """Agent 开始执行前调用。"""
```

**参数**：
- `memories`: 历史对话消息列表

**调用时机**：Agent `run()` 方法开始时

**用途**：初始化 Agent 状态、加载配置等

#### 2. `prepare_kwargs(thinking: bool = True)`
```python
async def prepare_kwargs(self, thinking: bool = True) -> dict:
    """准备 LLM 请求的 kwargs 参数。"""
    return {
        "stream_options": {"include_usage": True},
        "extra_body": {
            "thinking": {"type": "enabled" if thinking else "disabled"},
        }
    }
```

**参数**：
- `thinking`: 是否启用思考模式

**返回值**：传递给 LLM 的参数字典

**用途**：自定义 LLM 请求参数

#### 3. `prepare_tools(memories)`
```python
async def prepare_tools(self, memories: list[ChatCompletionMessageParam]) -> tuple[list[ChatCompletionToolParam], dict[str, ToolClosure]]:
    """准备 LLM 请求的工具列表和工具函数字典。"""
    return self.tools, self.tool_call_function
```

**参数**：
- `memories`: 当前对话记忆

**返回值**：`(工具列表, 工具函数字典)` 元组

**用途**：动态选择或过滤可用工具

#### 4. `on_iteration_start(iteration)`
```python
async def on_iteration_start(self, iteration: int) -> None:
    """每次循环开始前调用。"""
```

**参数**：
- `iteration`: 当前循环迭代次数

#### 5. `on_generate_start()`
```python
async def on_generate_start(self) -> None:
    """开始生成内容时调用。"""
```

#### 6. `on_generate_delta(delta)`
```python
async def on_generate_delta(self, delta: str) -> None:
    """接收到内容生成的每个 delta 时调用。"""
```

**参数**：
- `delta`: 从 LLM 流式接收的文本片段

#### 7. `on_generate_complete(content)`
```python
async def on_generate_complete(self, content: str) -> None:
    """内容生成完成时调用。"""
```

**参数**：
- `content`: 完整的生成内容

#### 8. `on_tool_calls_start_batch(tool_exec_data)`
```python
async def on_tool_calls_start_batch(self, tool_exec_data: dict[UUID, AgentRuntimeToolCallData]) -> None:
    """工具调用批次开始时调用。"""
```

**参数**：
- `tool_exec_data`: 工具执行数据字典，key 为 UUID，value 为 `AgentRuntimeToolCallData`

#### 9. `on_tool_call_start(tool_name, params)`
```python
async def on_tool_call_start(self, tool_name: str, params: dict) -> None:
    """单个工具调用开始时调用。"""
```

**参数**：
- `tool_name`: 工具名称
- `params`: 工具调用参数

#### 10. `on_tool_call_complete(tool_name, result)`
```python
async def on_tool_call_complete(self, tool_name: str, result: ToolTaskResult) -> None:
    """单个工具调用完成时调用。"""
```

**参数**：
- `tool_name`: 工具名称
- `result`: 工具执行结果

#### 11. `on_tool_call_error(tool_name, error)`
```python
async def on_tool_call_error(self, tool_name: str, error: BaseException) -> None:
    """单个工具调用出错时调用。"""
```

**参数**：
- `tool_name`: 工具名称
- `error`: 异常对象

#### 12. `on_tool_calls_complete_batch(tool_exec_data)`
```python
async def on_tool_calls_complete_batch(self, tool_exec_data: dict[UUID, AgentRuntimeToolCallData]) -> None:
    """工具调用响应处理完成时调用。"""
```

#### 13. `on_iteration_end(iteration, memories)`
```python
async def on_iteration_end(self, iteration: int, memories: list[ChatCompletionMessageParam]) -> None:
    """每次循环结束时调用。"""
```

**参数**：
- `iteration`: 当前循环迭代次数
- `memories`: 更新后的对话记忆

#### 14. `on_agent_complete()`
```python
async def on_agent_complete(self) -> None:
    """Agent 执行完成时调用。"""
```

#### 15. `on_agent_cancel()`
```python
async def on_agent_cancel(self) -> None:
    """Agent 被取消时调用。"""
```

---

### 同步生命周期方法

循环控制相关的方法为同步方法：

#### 1. `loop_flag_init()`
```python
def loop_flag_init(self) -> Any:
    """初始化循环标志，返回循环控制值。"""
    if self.loop_control:
        return self.loop_control
    return True
```

**返回值**：初始循环控制值

#### 2. `loop_flag_unset_on_iter_start(current_value, iteration)`
```python
def loop_flag_unset_on_iter_start(self, current_value: Any, iteration: int) -> Any:
    """每次循环开始时调用，返回新的循环控制值。"""
    return False
```

**参数**：
- `current_value`: 当前循环控制值
- `iteration`: 当前迭代次数

**返回值**：新的循环控制值

#### 3. `loop_flag_set_on_tool_calls(current_value)`
```python
def loop_flag_set_on_tool_calls(self, current_value: Any) -> Any:
    """当需要工具调用时调用，返回新的循环控制值。"""
    return True
```

**参数**：
- `current_value`: 当前循环控制值

**返回值**：新的循环控制值

#### 4. `loop_flag_should_continue(current_value)`
```python
def loop_flag_should_continue(self, current_value: Any) -> bool:
    """根据循环控制值判断是否继续循环。"""
    return bool(current_value)
```

**参数**：
- `current_value`: 当前循环控制值

**返回值**：是否继续循环

---

## 当前继承模式及其局限性

### 现有模式

当前系统通过继承 `AgentBase` 并覆盖生命周期方法来实现自定义 Agent：

```python
class MainAgent(AgentBase):
    def __init__(self, streaming_processor, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.streaming_processor = streaming_processor

    async def on_generate_delta(self, delta: str):
        await self.streaming_processor.push_text_delta_msg(delta)

    async def on_tool_call_start(self, tool_name: str, params: dict):
        # 自定义工具调用开始行为
        pass
```

### 局限性

1. **代码重用困难**
   - 多个 Agent 需要相同功能时，必须创建中间基类
   - 导致继承层次加深，形成"基类爆炸"

2. **功能组合僵化**
   - 难以在运行时动态组合不同功能
   - 无法灵活选择需要的功能模块

3. **维护复杂度高**
   - 深层继承链难以理解和追踪
   - 修改基类可能影响所有子类

4. **违反组合优于继承原则**
   - 紧耦合的继承关系
   - 难以进行单元测试和模拟

---

## 相关代码基础设施

### 类型定义

**ToolClosure 类型** (`api/agent/tools/type.py`):
```python
from collections.abc import Callable, Coroutine
from typing import Any
from .data_model import ToolTaskResult

ToolClosure = Callable[..., Coroutine[Any, Any, ToolTaskResult]]
```

### 工具系统

工具通过构造器模式注册，每个工具有对应的配置类和构造函数：
- 工具配置：`TodoWriteConfig`、`AskUserConfig` 等
- 工具构造：`construct_todo_write()`、`construct_ask_user()` 等
- 工具工厂：`ToolFactory` 统一管理工具创建

### OpenAI 类型

使用 `openai` 包的类型定义：
- `ChatCompletionToolParam`：工具参数定义
- `ChatCompletionMessageToolCall`：工具调用对象
- `ChatCompletionMessageParam`：消息参数
- `CompletionUsage`：API 使用统计

### 日志系统

使用 `logfire` 进行结构化日志记录，配合 `LangFuseSpanAttributes` 追踪执行过程。

### 负载均衡

通过 `LOAD_BLANCER` 执行 LLM 请求委托：
```python
result = await LOAD_BLANCER.execute(service_name, delegate)
```

---

## 相关文件

- [AgentBase 完整实现](../../../../api/agent/base_agent.py)
- [工具类型定义](../../../../api/agent/tools/type.py)
- [工具数据模型](../../../../api/agent/tools/data_model.py)
- [MainAgent 示例](../../../../api/agent/strategy/main_agent.py)
