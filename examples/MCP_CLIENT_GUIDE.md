# MCP 客户端实现指南

本文档介绍如何实现 MCP (Model Context Protocol) 客户端，包括主要接口、meta 信息传递、以及服务端向客户端的消息投递机制。

## 目录

- [基础概念](#基础概念)
- [客户端实现](#客户端实现)
- [主要接口](#主要接口)
- [Meta 信息传递](#meta-信息传递)
- [服务端消息投递](#服务端消息投递)
- [完整示例](#完整示例)
- [常见问题](#常见问题)

---

## 基础概念

### MCP Streamable-HTTP 模式

MCP 支持 Streamable-HTTP 传输模式，使用 HTTP POST 请求和 SSE (Server-Sent Events) 流进行双向通信：

```
客户端                                           服务端
  │                                                │
  │ ─────────── POST /mcp (请求) ──────────────► │
  │                                                │
  │ ◄───────── SSE 响应流 (长连接) ─────────────── │
  │     ├─ 日志通知 (LoggingMessageNotification)  │
  │     ├─ 进度通知 (ProgressNotification)        │
  │     └─ 最终响应 (CallToolResult)              │
  │                                                │
  │ ─────────── GET /mcp (建立连接) ────────────► │
  │                                                │
  │ ◄───────── SSE 推送流 (长连接) ─────────────── │
  │     └─ 服务端主动推送的消息                    │
```

### 响应模式

MCP 服务端支持两种响应模式：

| 模式 | `json_response` | 特点 |
|------|----------------|------|
| JSON 模式 | `True` | 只返回最终响应，不传输通知 |
| SSE 模式 | `False` | 通过 SSE 流传输所有消息（推荐） |

**重要**：要接收服务端的日志和进度通知，必须使用 SSE 模式（`json_response=False`）。

---

## 客户端实现

### 1. 基本连接

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    # 建立 Streamable-HTTP 连接
    async with streamable_http_client("http://localhost:8000/mcp") as (
        read_stream,
        write_stream,
        get_session_id,
    ):
        # 创建会话
        async with ClientSession(read_stream, write_stream) as session:
            # 初始化连接
            result = await session.initialize()
            print(f"已连接: {result.serverInfo.name}")

            # 使用会话...
            await session.call_tool(...)


if __name__ == "__main__":
    asyncio.run(main())
```

### 2. 注册回调函数

```python
async def logging_callback(params):
    """处理服务端日志"""
    level = params.level  # "debug", "info", "warning", "error"
    data = params.data
    print(f"[{level.upper()}] {data}")


async def progress_callback(progress: float, total: float | None, message: str | None):
    """处理进度更新"""
    if total:
        percentage = progress / total * 100
        print(f"进度: {percentage:.1f}% - {message or ''}")
    else:
        print(f"进度: {progress} - {message or ''}")


# 创建会话时注册回调
async with ClientSession(
    read_stream,
    write_stream,
    logging_callback=logging_callback,  # 日志回调
) as session:
    ...
```

---

## 主要接口

### ClientSession 核心方法

| 方法 | 说明 | 返回类型 |
|------|------|----------|
| `initialize()` | 初始化连接 | `InitializeResult` |
| `list_tools()` | 列出可用工具 | `ListToolsResult` |
| `call_tool()` | 调用工具 | `CallToolResult` |
| `list_resources()` | 列出资源 | `ListResourcesResult` |
| `read_resource()` | 读取资源 | `ReadResourceResult` |
| `send_notification()` | 发送通知 | `None` |

### 工具调用

```python
result = await session.call_tool(
    name="ToolName",           # 工具名称
    arguments={...},           # 工具参数
    progress_callback=cb,      # 进度回调（可选）
    meta={...},                # 元数据（可选）
)

# 处理返回结果
for content in result.content:
    if hasattr(content, "text"):
        print(content.text)  # 文本内容
    elif hasattr(content, "data"):
        print(content.data)  # 图片/资源数据
```

---

## Meta 信息传递

### 什么是 Meta

Meta (元数据) 是客户端向服务端传递的额外信息，用于：
- 关联请求和响应
- 传递进度 token
- 自定义上下文信息

### Meta 参数

在 `call_tool()` 中传递 meta：

```python
result = await session.call_tool(
    "ToolName",
    {"param": "value"},
    meta={
        "customField": "customValue",  # 自定义字段
        "requestId": "123",            # 请求标识
        # ... 其他自定义字段
    }
)
```

### 进度 Token

使用 `progress_callback` 时，客户端自动设置 `progressToken`：

```python
# 方式1：使用 progress_callback（推荐）
result = await session.call_tool(
    "LongRunningTool",
    {"param": "value"},
    progress_callback=my_progress_callback,  # 自动设置 progressToken
)

# 方式2：手动设置 progressToken
result = await session.call_tool(
    "LongRunningTool",
    {"param": "value"},
    meta={"progressToken": "my-token-123"},
    progress_callback=my_progress_callback,
)
```

### 服务端接收 Meta

```python
@server.tool()
def my_tool(param: str, ctx: Context) -> str:
    # 获取 meta 信息
    if ctx.request_context.meta:
        custom_field = ctx.request_context.meta.get("customField")
        progress_token = ctx.request_context.meta.progressToken if ctx.request_context.meta else None

    return "result"
```

---

## 服务端消息投递

### 1. 日志消息

服务端通过 `Context` 对象发送日志：

```python
from mcp.server.fastmcp import Context

@server.tool()
async def my_tool(ctx: Context) -> str:
    # 发送不同级别的日志
    await ctx.debug("调试信息")
    await ctx.info("普通信息")
    await ctx.warning("警告信息")
    await ctx.error("错误信息")

    return "done"
```

**日志级别**：
- `debug` - 调试信息
- `info` - 普通信息
- `warning` - 警告信息
- `error` - 错误信息

### 2. 进度通知

```python
@server.tool()
async def long_running_tool(ctx: Context) -> str:
    total = 100
    for i in range(total + 1):
        # 发送进度更新
        await ctx.report_progress(
            progress=i,       # 当前进度
            total=total,      # 总量（可选）
            message=f"处理中 {i}%"  # 消息（可选）
        )
        # 执行工作...
        await asyncio.sleep(0.1)

    return "done"
```

### 3. 消息路由

在 SSE 模式下，所有通知通过工具调用的 SSE 响应流传输：

```
工具调用 SSE 流:
  ├─ 日志通知
  ├─ 进度通知
  └─ 最终响应
```

**重要**：日志和进度通知会在工具执行过程中实时发送，客户端可以同步接收。

---

## 完整示例

### 客户端完整代码

```python
"""MCP 客户端完整示例"""

import asyncio
from datetime import datetime
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def logging_callback(params):
    """处理服务端日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    level = params.level
    data = params.data

    symbols = {"debug": "🐛", "info": "ℹ️", "warning": "⚠️", "error": "❌"}
    symbol = symbols.get(level, "📝")

    print(f"[{timestamp}] {symbol} [{level.upper()}] {data}")


async def progress_callback(progress: float, total: float | None, message: str | None):
    """处理进度更新"""
    if total:
        bar_length = 30
        filled = int(bar_length * progress / total)
        bar = "█" * filled + "░" * (bar_length - filled)
        percentage = progress / total * 100
        print(f"  ⏳ [{bar}] {percentage:.1f}%  {message or ''}")
    else:
        print(f"  ⏳ 进度: {progress}  {message or ''}")


async def main():
    server_url = "http://localhost:8000/mcp"

    async with streamable_http_client(server_url) as (
        read_stream,
        write_stream,
        get_session_id,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
            logging_callback=logging_callback,
        ) as session:
            # 初始化
            init_result = await session.initialize()
            print(f"✓ 已连接到: {init_result.serverInfo.name}")
            print(f"✓ 协议版本: {init_result.protocolVersion}\n")

            # 列出工具
            tools = await session.list_tools()
            print(f"可用工具: {[t.name for t in tools.tools]}\n")

            # 调用带进度的工具
            result = await session.call_tool(
                "LongRunningTool",
                {"seconds": 5},
                meta={"customField": "test"},  # 传递 meta 信息
                progress_callback=progress_callback,
            )

            # 打印结果
            for content in result.content:
                if hasattr(content, "text"):
                    print(f"\n结果: {content.text}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 服务端完整代码

```python
"""MCP 服务端工具示例"""

import asyncio
from mcp_server.constant import MCP_SERVER
from mcp.server.fastmcp import Context


@MCP_SERVER.tool(name="LongRunningTool")
async def long_running_tool(seconds: int = 5, ctx: Context = None) -> str:
    """
    长时间运行的工具，演示日志和进度通知
    """
    await ctx.debug("开始执行工具")
    await ctx.info(f"将运行 {seconds} 秒...")

    total = 100
    for i in range(total + 1):
        await asyncio.sleep(seconds / total)

        # 发送进度
        await ctx.report_progress(i, total, f"处理中 {i}%")

        # 在关键节点发送日志
        if i == 25:
            await ctx.info("已完成 25%")
        elif i == 50:
            await ctx.warning("已达到 50%")
        elif i == 75:
            await ctx.info("已完成 75%")

    await ctx.info("执行完成！")
    return f"完成！运行了 {seconds} 秒"
```

### 服务端配置

```python
# mcp_server/constant.py

from pathlib import Path
from mcp.server.fastmcp import FastMCP

# ⚠️ 重要：必须设置为 False 才能传输通知
MCP_SERVER = FastMCP(
    "server-name",
    json_response=False,  # 使用 SSE 模式
    host="0.0.0.0"
)
```

---

## 常见问题

### Q: 为什么接收不到日志消息？

**A**: 检查服务端配置：
```python
# 错误配置
MCP_SERVER = FastMCP("name", json_response=True)  # ❌

# 正确配置
MCP_SERVER = FastMCP("name", json_response=False)  # ✅
```

### Q: 进度回调不工作？

**A**: 确保：
1. 使用了 `progress_callback` 参数
2. 服务端调用了 `ctx.report_progress()`
3. `json_response=False`

### Q: 如何传递自定义 meta 信息？

**A**:
```python
# 客户端
await session.call_tool("Tool", {...}, meta={"key": "value"})

# 服务端
meta = ctx.request_context.meta
custom_value = meta.get("key") if meta else None
```

### Q: 日志和进度有什么区别？

**A**:
- **日志**：用于记录信息，通过 `logging_callback` 接收
- **进度**：用于报告任务进度，通过 `progress_callback` 接收，通常与 `progressToken` 关联

---

## 参考资料

- [MCP 规范](https://modelcontextprotocol.io/)
- [FastMCP 文档](https://github.com/jlowin/fastmcp)
- [示例代码](./client_test.py)
