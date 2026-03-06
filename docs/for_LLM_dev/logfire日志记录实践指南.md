# Logfire 日志记录实践指南

本文档为 IDIOT 项目中的 logfire 使用提供详细的实践建议，旨在帮助开发者在未来的开发中正确、高效地使用日志记录。

---

## 目录

1. [架构概述](#架构概述)
2. [Logfire 与 Loguru 的职责划分](#logfire-与-loguru-的职责划分)
3. [核心配置](#核心配置)
4. [使用模式](#使用模式)
5. [Langfuse 集成](#langfuse-集成)
6. [实践建议](#实践建议)
7. [常见问题与解决方案](#常见问题与解决方案)

---

## 架构概述

IDIOT 项目采用**双日志系统架构**，结合了 logfire（分布式追踪）和 loguru（传统日志记录）两种工具的优势。

```
┌─────────────────────────────────────────────────────────────────┐
│                        应用程序代码                              │
└───────────────────────────────┬─────────────────────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│        logfire          │         │         loguru          │
│   (分布式追踪/可观测性)  │         │    (传统日志记录)        │
│                         │         │                         │
│  - Span 创建            │         │  - 本地文件日志          │
│  - Baggage 上下文传递   │         │  - stderr 错误输出       │
│  - OpenTelemetry 集成   │         │  - 调试信息              │
└───────────┬─────────────┘         └─────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LoguruSpanProcessor (桥接器)                  │
│              将 logfire span 同步转发到 loguru                   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│   OpenTelemetry         │         │      本地文件系统        │
│   Collector             │         │                         │
│         ↓               │         │   ~/.cache/idiot/logs/  │
│   Langfuse              │         │   └── app.log           │
│   (追踪数据后端)         │         │                         │
└─────────────────────────┘         └─────────────────────────┘
```

---

## Logfire 与 Loguru 的职责划分

### Logfire 使用场景

| 场景 | 说明 | 示例 |
|------|------|------|
| **Agent 执行追踪** | 追踪 Agent 的完整执行流程 | `base_agent.py::run` |
| **LLM 调用追踪** | 记录 LLM API 调用及错误 | `generator.py` 中的 API 错误处理 |
| **图执行追踪** | 追踪 DAG 图的节点执行 | `graph_core.py` 中的节点执行 |
| **任务级追踪** | 会话任务的整体追踪 | `chat_task.py::session_chat_task` |
| **MCP 工具调用** | MCP 服务器的日志转发 | `mcp/client.py` 中的日志处理 |

### Loguru 使用场景

| 场景 | 说明 | 示例 |
|------|------|------|
| **文件系统操作** | 文件读写、目录操作等 | `fs_utils/*.py` |
| **WebSocket 管理** | 连接状态、消息处理 | `ws_worker.py` |
| **HTTP 长轮询** | 轮询状态、超时处理 | `http_worker/*.py` |
| **应用启动/关闭** | 服务初始化、优雅关闭 | `graceful_shutdown.py` |
| **JuiceFS 操作** | 存储相关操作 | `juiceFS/creator.py` |

### 选择原则

```
是否涉及分布式追踪？
    ├── 是 → 使用 logfire
    │      (跨服务调用、Agent 执行、LLM 调用、图执行)
    │
    └── 否 → 是否需要本地调试？
              ├── 是 → 使用 loguru
              │        (文件操作、连接管理、本地状态)
              │
              └── 否 → 考虑是否需要日志
```

---

## 核心配置

### 初始化配置

**文件位置**: `api/logger/logger.py`

```python
def init_logger():
    # 1. 配置 loguru 文件日志
    logger.add(str(LOG_DIR / "app.log"), rotation="100 MB", level="DEBUG")
    logger.add(sink=sys.stderr, level="ERROR")

    # 2. 配置 logfire (可选，需要设置环境变量)
    if LOGFIRE_LOG_ENDPOINT:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = LOGFIRE_LOG_ENDPOINT
        logfire.configure(
            service_name="test_service",
            send_to_logfire=False,  # 发送到自定义 OTEL 端点
            additional_span_processors=[LoguruSpanProcessor()],  # 桥接到 loguru
            scrubbing=False,
        )
```

### 环境变量

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `LOGFIRE_LOG_ENDPOINT` | OpenTelemetry Collector 端点 | `http://localhost:4318` |
| `LANGFUSE_ENDPOINT` | Langfuse 服务端点 | `http://localhost:3000/api/public/otel` |

### LoguruSpanProcessor 桥接器

将 logfire 的 span 信息同步到 loguru，实现统一的日志查看：

```python
class LoguruSpanProcessor(SpanProcessor):
    def on_start(self, span: Span, parent_context=None):
        if span.attributes.get("forword_to_loguru", True):
            if span_level := span.attributes.get(ATTRIBUTES_LOG_LEVEL_NUM_KEY):
                logger.log(span_level, span.name)
            else:
                logger.info(span.name)
```

---

## 使用模式

### 模式 1: Span 创建与追踪

用于追踪函数执行的完整生命周期。

```python
import logfire
from api.logger.datamodel import LangFuseSpanAttributes

async def run(self, memories: list, service_name: str):
    langfuse_observation_attributes = LangFuseSpanAttributes(
        observation_type="span",
    )

    with logfire.span(
        "api/agent/base_agent.py::run",
        **langfuse_observation_attributes.model_dump(mode="json", by_alias=True)
    ) as span:
        return await self.__run(memories, service_name)
```

**适用场景**:
- Agent 执行入口
- 任务处理函数
- 图节点执行

### 模式 2: Baggage 上下文传递

`set_baggage` 用于设置 Langfuse **Trace 级别**属性，使追踪数据在 Langfuse 平台中能够按 `user_id` 或 `session_id` 聚合。

**重要**: 仅在涉及 `user_id` 或 `session_id` 时使用 `set_baggage`。无此上下文时，直接使用 `logfire.span()` 即可。

```python
import logfire
from api.logger.datamodel import LangFuseTraceAttributes, LangFuseSpanAttributes

async def session_chat_task(user_id: UUID, session_id: UUID, session_task_id: UUID, ...):
    # 设置 Trace 级别的上下文（用于 Langfuse 聚合）
    langfuse_trace_attributes = LangFuseTraceAttributes(
        name="api/chat/chat_task.py::session_chat_task",
        user_id=str(user_id),
        session_id=str(session_id),
        metadata={
            "session_task_id": str(session_task_id),
        }
    )

    # Baggage 会在整个调用链中传递
    with logfire.set_baggage(**langfuse_trace_attributes.model_dump(mode="json", by_alias=True)):
        langfuse_observation_attributes = LangFuseSpanAttributes(observation_type="span")

        with logfire.span("api/chat/chat_task.py::session_chat_task",
                          **langfuse_observation_attributes.model_dump(mode="json", by_alias=True)):
            return await __session_chat_task(...)
```

**选择指导**:
- 有 `user_id` 或 `session_id` → 使用 `set_baggage` + `LangFuseTraceAttributes`
- 无 user/session 上下文 → 仅使用 `logfire.span()`，避免滥用 `set_baggage`

**适用场景**:
- 用户会话任务（需按用户/会话聚合追踪）
- 跨多个函数调用且需关联用户身份的追踪

### 模式 3: 日志级别使用

```python
import logfire

# info: 正常流程的关键节点
logfire.info("Node execution started", node_name=node_name)

# warning: 可恢复的异常或重试
logfire.warning(f"Retrying... OpenAI API Error Code {e.code}. Error: {e.message}")

# error: 不可恢复的错误
logfire.error(f"Unexpected OpenAI API Error Code {e.code}. Error: {e.message}")

# debug: 详细调试信息
logfire.debug("MCP server log", mcp_log_data=log_data)
```

### 模式 4: 嵌套 Span

用于表达执行层级关系。

```python
import logfire

async def execute_graph(self):
    # 层级 1: 整个图的执行
    with logfire.span(f"Graph {self.name}"):
        for node in nodes:
            # 层级 2: 单个节点的执行
            with logfire.span(f"Graph {self.name}::{node}"):
                if node in finalized_nodes:
                    logfire.info(f"Node {node} is already finalized")
                else:
                    await execute_node(node)
```

**输出的层级结构**:
```
Graph workflow_main
├── Graph workflow_main::NodeA
│   └── logfire.info: "Node NodeA is already finalized"
├── Graph workflow_main::NodeB
│   └── ...
└── Graph workflow_main::NodeC
```

### 模式 5: 装饰器方式

使用 `@log_span` 装饰器简化代码。

```python
from api.logger.logger import log_span

@log_span(
    "处理用户请求",
    args_captured_as_tags=['user_id'],      # 捕获参数作为标签
    only_tags_kwargs=['!trace_id'],         # 仅作为标签，不传递给函数
)
async def handle_request(user_id: int, **kwargs):
    # 函数执行时会产生名为"处理用户请求"的 span
    # 标签: {'user_id': 实际参数值, '!trace_id': ...}
    pass

# 调用方式
await handle_request(user_id=123, **{"!trace_id": "fd0bc3b2-..."})
```

---

## Langfuse 集成

### 数据模型

项目定义了两个 Pydantic 模型用于结构化追踪数据：

#### LangFuseTraceAttributes (Trace 级别)

```python
from api.logger.datamodel import LangFuseTraceAttributes

attributes = LangFuseTraceAttributes(
    name="trace_name",              # Trace 名称
    user_id="user_123",             # 用户 ID
    session_id="session_456",       # 会话 ID
    release="v1.0.0",              # 发布版本
    tags=["production", "api"],     # 标签列表
    metadata={                      # 元数据 (必须是扁平字典)
        "session_task_id": "task_789",
        "environment": "production",
    },
    input={"query": "hello"},       # 输入数据
    output={"response": "world"},   # 输出数据
)
```

#### LangFuseSpanAttributes (Observation/Span 级别)

```python
from api.logger.datamodel import LangFuseSpanAttributes

attributes = LangFuseSpanAttributes(
    observation_type="span",        # 类型: span, generation, event
    level="DEFAULT",               # 级别: DEBUG, DEFAULT, WARNING, ERROR
    metadata={                      # 元数据
        "mcp_server_name": "filesystem",
    },
    input={"messages": [...]},      # 输入
    output={"content": "..."},      # 输出
    model_name="gpt-4",            # 模型名称 (仅 generation 类型)
    model_parameters='{"temperature": 0.7}',  # 模型参数
    usage_details={                 # Token 使用量
        "input": 100,
        "output": 50,
    },
)
```

### OpenTelemetry Collector 配置

**文件位置**: `otel_collector/otel-collector-config-connector.yml`

```yaml
exporters:
  otlphttp/langfuse:
    endpoint: ${env:LANGFUSE_ENDPOINT:-http://host.docker.internal:3000/api/public/otel}
    headers:
      # Basic Auth: Base64(public_key:secret_key)
      Authorization: "Basic cGstbGYt..."

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [spanmetrics, otlphttp/langfuse]
```

---

## 实践建议

### 1. Span 命名规范

使用清晰的命名模式，便于在追踪系统中识别：

```
推荐格式: <模块路径>::<函数名>

示例:
- api/agent/base_agent.py::run
- api/chat/chat_task.py::session_chat_task
- api/graph_executor/graph_core.py::start
```

### 2. 元数据扁平化

Langfuse 要求 metadata 必须是扁平字典，不支持嵌套：

```python
# 正确
metadata = {
    "session_task_id": "task_123",
    "environment": "production",
}

# 错误 - 会导致验证失败
metadata = {
    "task": {
        "id": "task_123",  # 嵌套字典不支持
    }
}
```

### 3. 异常处理模式

```python
import logfire
import traceback

async def process_task():
    try:
        # 业务逻辑
        pass
    except ExpectedException as e:
        # 可预期的异常，使用 warning
        logfire.warning(f"Task retry needed: {e}")
        raise
    except Exception as e:
        # 未预期的异常，使用 error
        logfire.error(
            "process_task#unhandled_exception",
            traceback=traceback.format_exc()
        )
        # 保存异常堆栈
        await save_exception_stack_async(e, "process_task")
        raise
```

### 4. 敏感信息处理

logfire 默认会 scrubbing 敏感信息。如需禁用：

```python
logfire.configure(
    scrubbing=False,  # 禁用自动敏感信息过滤
)
```

**注意**: 禁用后需自行确保不记录敏感数据。

### 5. 条件性启用

根据环境变量决定是否启用 logfire：

```python
if LOGFIRE_LOG_ENDPOINT:
    logfire.configure(...)
```

这允许在开发环境中禁用追踪，在生产环境中启用。

### 6. 合理使用日志级别

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| `debug` | 详细调试信息，生产环境通常关闭 | MCP 消息内容 |
| `info` | 正常流程的关键节点 | 任务开始、节点完成 |
| `warning` | 可恢复的异常、重试场景 | API 限流、降级处理 |
| `error` | 不可恢复的错误、任务终止 | 未预期异常、超时 |

---

## 常见问题与解决方案

### Q1: logfire 和 loguru 同时使用会重复记录吗？

**不会**。默认情况下 logfire 的 span 不会自动发送到 loguru。只有通过 `LoguruSpanProcessor` 桥接器，并且 `forword_to_loguru=True` 时才会同步。

### Q2: 如何在追踪中传递自定义属性？

```python
with logfire.span("operation") as span:
    span.set_attribute("custom.key", "value")
```

### Q3: 如何禁用某个 span 的 loguru 转发？

```python
with logfire.span("operation", forward_to_loguru=False):
    # 此 span 不会转发到 loguru
    pass
```

### Q4: metadata 验证失败怎么办？

确保 metadata 是扁平字典，不包含嵌套对象：

```python
# LangFuseSpanAttributes 会自动验证
attributes = LangFuseSpanAttributes(
    metadata={"key": "value"}  # 正确
)
```

### Q5: 如何查看本地日志？

```bash
# 查看 loguru 日志
tail -f ~/.cache/idiot/logs/app.log

# 在 Langfuse 中查看追踪数据
# 访问 Langfuse Web UI
```

---

## 依赖版本

```toml
# pyproject.toml
dependencies = [
    "logfire>=3.21.1",
    "loguru>=0.7.3",
    "langfuse>=3.6.1",
    "opentelemetry-sdk>=1.20.0",
]
```

---

## 参考文件

| 文件路径 | 说明 |
|-----------|------|
| `api/logger/logger.py` | 核心配置、装饰器、桥接器 |
| `api/logger/datamodel.py` | Langfuse 数据模型 |
| `api/logger/constant.py` | 常量定义 |
| `api/chat/chat_task.py` | 完整使用示例 |
| `api/agent/base_agent.py` | Agent 追踪示例 |
| `api/graph_executor/graph_core.py` | 图执行追踪示例 |
| `api/llm/generator.py` | 错误处理示例 |
| `otel_collector/otel-collector-config-connector.yml` | OTLP 配置 |