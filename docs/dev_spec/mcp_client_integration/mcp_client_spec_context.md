---
文档标题：mcp_client_spec_context
文档描述：描述 MCP Client 模块开发的上下文，包括现有代码基础设施和相关依赖。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [项目概述](#项目概述)
- [现有工具系统](#现有工具系统)
- [MCP 协议](#mcp-协议)
- [相关文件索引](#相关文件索引)

---

## 项目概述

IDIOT (Intelligent Development Integrated & Operations Toolkit) 是一个基于 Python 的 AI 应用程序后端工具包。本次开发旨在为 IDIOT 添加 MCP (Model Context Protocol) Client 功能，使 agent 能够调用 MCP server 提供的工具。

**关键开发约束**：
- MCP 模块与现有 ToolFactory 体系完全解耦
- MCP 模块是独立的 ToolClosure 生产者
- 不修改现有的 agent 实现

---

## 现有工具系统

### ToolClosure 类型定义

ToolClosure 是工具调用的函数签名约定，定义在 [`../../api/agent/tools/type.py`](../../api/agent/tools/type.py):

```python
ToolClosure = Callable[..., Coroutine[Any, Any, ToolTaskResult]]
```

### ToolTaskResult 数据模型

工具执行返回的结果，定义在 [`../../api/agent/tools/data_model.py`](../../api/agent/tools/data_model.py):

```python
class ToolTaskResult(BaseModel):
    str_content: str  # 字符串形式的执行结果
    json_content: dict | None = None  # 结构化数据结果
    occur_error: bool = False  # 是否发生错误
    HIL_data: list[HILInterruptContent] | None = None  # 人机循环数据
    u2a_session_link_data: U2ASessionLinkData | None = None  # 用户到代理会话链接
    a2a_session_link_data: A2ASessionLinkData | None = None  # 代理到代理会话链接
```

### 现有工具示例

参考 [`../../api/agent/tools/todo/constructor.py`](../../api/agent/tools/todo/constructor.py):

```python
class TodoWriteTool(object):
    def __init__(self, config: TodoWriteConfig, storage_backend: TodoStorageBackend):
        self.config = config
        self.storage_backend = storage_backend

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 参数验证
        try:
            param = TodoWriteParamDefine.model_validate(kwargs)
        except ValidationError as e:
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}",
                occur_error=True
            )

        # 业务逻辑
        ...

        return ToolTaskResult(str_content="操作成功")
```

---

## MCP 协议

### Streamable-HTTP 模式

MCP 使用 HTTP + SSE (Server-Sent Events) 进行双向通信：

```
客户端                                           服务端
  │                                                │
  │ ─────────── POST /mcp (请求) ──────────────► │
  │                                                │
  │ ◄───────── SSE 响应流 (长连接) ─────────────── │
  │     ├─ 日志通知 (LoggingMessageNotification)  │
  │     ├─ 进度通知 (ProgressNotification)        │
  │     └─ 最终响应 (CallToolResult)              │
```

### MCP Client API

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# 建立连接
async with streamable_http_client(url) as (read_stream, write_stream, get_session_id):
    async with ClientSession(read_stream, write_stream) as session:
        # 初始化
        await session.initialize()

        # 获取工具列表
        tools = await session.list_tools()

        # 调用工具
        result = await session.call_tool(name, arguments)
```

### MCP 工具信息结构

```python
Tool(
    name="ToolName",
    description="工具描述",
    inputSchema={
        "type": "object",
        "properties": {...},
        "required": [...]
    }
)
```

---

## 相关文件索引

### 项目基础设施

| 文件路径 | 说明 |
|---------|------|
| [`../../api/agent/tools/type.py`](../../api/agent/tools/type.py) | ToolClosure 类型定义 |
| [`../../api/agent/tools/data_model.py`](../../api/agent/tools/data_model.py) | ToolTaskResult 数据模型 |
| [`../../api/agent/tools/config_data_model.py`](../../api/agent/tools/config_data_model.py) | SessionToolConfigBase 基类 |
| [`../../api/agent/tools/tool_factory/tool_factory.py`](../../api/agent/tools/tool_factory/tool_factory.py) | 工具工厂 |
| [`../../api/agent/tools/tool_factory/tool_init_function.py`](../../api/agent/tools/tool_factory/tool_init_function.py) | 工具构造函数注册 |
| [`../../api/chat/chat_task.py`](../../api/chat/chat_task.py) | 聊天任务（工具初始化） |

### MCP 参考文档

| 文件路径 | 说明 |
|---------|------|
| [`../../examples/MCP_CLIENT_GUIDE.md`](../../examples/MCP_CLIENT_GUIDE.md) | MCP Client 实现指南 |

### 工具示例

| 文件路径 | 说明 |
|---------|------|
| [`../../api/agent/tools/todo/`](../../api/agent/tools/todo/) | TODO 工具完整实现 |
| [`../../api/agent/tools/todo/config_data_model.py`](../../api/agent/tools/todo/config_data_model.py) | 配置模型示例 |
| [`../../api/agent/tools/todo/constructor.py`](../../api/agent/tools/todo/constructor.py) | 构造函数示例 |

---

## Python 依赖

```toml
# pyproject.toml
[project.dependencies]
mcp = "*"
```

MCP SDK 提供：
- `ClientSession`: 会话管理
- `streamable_http_client`: Streamable-HTTP 传输
- 工具调用和数据类型定义
