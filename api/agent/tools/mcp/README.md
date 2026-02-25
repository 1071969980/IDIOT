# MCP Client 模块

MCP (Model Context Protocol) Client 模块，为 IDIOT Agent 提供访问 MCP Server 工具的能力。

## 概述

MCP 模块是一个独立的 ToolClosure 生产者，与现有的 ToolFactory 体系完全解耦。它负责：

- 连接到一个或多个 MCP Server
- 发现和过滤可用的工具
- 将 MCP 工具转换为 Agent 可用的 ToolClosure
- 管理 MCP 连接的生命周期（Per-Agent-Run）

## 快速开始

```python
from api.agent.tools.mcp import (
    load_mcp_tools,
    McpClientConfig,
    McpServerConfig,
    McpToolFilter
)

# 配置 MCP Server
config = McpClientConfig(
    servers=[
        McpServerConfig(
            url="http://localhost:8000/mcp",
            name="my_tools",
            tool_filter=McpToolFilter(
                allow_list=["calculator", "search"]
            )
        )
    ]
)

# 加载工具
async with load_mcp_tools(config) as loader:
    tool_params, tool_closures = loader.get_tools()

    # 传入 Agent
    agent = BaseAgent(
        tools=tool_params,
        tool_call_function=tool_closures,
        ...
    )

    await agent.run()

# 连接自动关闭
```

## 配置说明

### McpServerConfig

单个 MCP Server 的配置。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | `str` | *必需* | MCP Server 的 streamable HTTP URL |
| `name` | `str` | `"default"` | Server 名称，用于日志和工具名称前缀 |
| `timeout` | `float` | `30.0` | 连接和调用超时时间（秒） |
| `tool_filter` | `McpToolFilter` | 默认过滤器 | 工具过滤配置 |

### McpToolFilter

工具过滤配置。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `allow_list` | `list[str] \| None` | `None` | 白名单，为 None 时允许所有工具 |
| `deny_list` | `list[str]` | `[]` | 黑名单，排除的工具列表 |

**过滤优先级**：
1. 先检查黑名单：在黑名单中 → 排除
2. 再检查白名单：白名单为 None → 包含；在白名单中 → 包含；不在 → 排除

### McpClientConfig

MCP Client 总配置。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `True` | 是否启用 MCP Client |
| `servers` | `list[McpServerConfig]` | *必需* | 要连接的 MCP Server 列表 |
| `include_server_name_in_tool_name` | `bool` | `True` | 是否在工具名称前添加 server 前缀 |
| `json_response` | `bool` | `False` | MCP 响应模式（False=SSE, True=JSON） |

## API 文档

### `load_mcp_tools(config: McpClientConfig) -> McpToolsLoader`

主入口函数，创建 MCP 工具加载器。

**参数**：
- `config`: MCP Client 配置

**返回**：
- `McpToolsLoader` 实例，需要使用 `async with` 进入上下文

### `class McpToolsLoader`

MCP 工具加载器，管理连接生命周期。

**方法**：
- `get_tools() -> tuple[list[ChatCompletionToolParam], dict[str, ToolClosure]]`
  - 获取工具列表

## 使用示例

### 基本使用

```python
from api.agent.tools.mcp import load_mcp_tools, McpClientConfig, McpServerConfig

config = McpClientConfig(
    servers=[McpServerConfig(url="http://localhost:8000/mcp", name="test")]
)

async with load_mcp_tools(config) as loader:
    tool_params, tool_closures = loader.get_tools()
    print(f"加载了 {len(tool_params)} 个工具")
```

### 多 Server 配置

```python
config = McpClientConfig(
    servers=[
        McpServerConfig(url="http://localhost:8000/mcp", name="tools"),
        McpServerConfig(url="http://localhost:8001/mcp", name="calc")
    ],
    include_server_name_in_tool_name=True
)

async with load_mcp_tools(config) as loader:
    tool_params, tool_closures = loader.get_tools()
    # 工具名称会带上前缀，如 "tools__search", "calc__add"
```

### 工具过滤

```python
from api.agent.tools.mcp import McpToolFilter

# 仅允许特定工具
config = McpClientConfig(
    servers=[
        McpServerConfig(
            url="http://localhost:8000/mcp",
            name="test",
            tool_filter=McpToolFilter(
                allow_list=["calculator", "search"]
            )
        )
    ]
)

# 排除特定工具
config = McpClientConfig(
    servers=[
        McpServerConfig(
            url="http://localhost:8000/mcp",
            name="test",
            tool_filter=McpToolFilter(
                deny_list=["dangerous_tool"]
            )
        )
    ]
)
```

### 多 Server 独立过滤

```python
# 每个 Server 可以有独立的过滤配置
config = McpClientConfig(
    servers=[
        McpServerConfig(
            url="http://localhost:8000/mcp",
            name="tools",
            tool_filter=McpToolFilter(allow_list=["search", "read"])
        ),
        McpServerConfig(
            url="http://localhost:8001/mcp",
            name="calc",
            tool_filter=McpToolFilter(deny_list=["internal_func"])
        )
    ],
    include_server_name_in_tool_name=True
)
```

## 错误处理

### 连接失败

如果 MCP Server 连接失败，`load_mcp_tools` 会抛出异常：

```python
try:
    async with load_mcp_tools(config) as loader:
        tool_params, tool_closures = loader.get_tools()
except Exception as e:
    print(f"连接失败: {e}")
```

### 工具调用失败

如果工具调用失败，会返回包含错误信息的 `ToolTaskResult`：

```python
result = await tool_closures["test__calculator"](a=1, b=2)
if result.occur_error:
    print(f"工具调用失败: {result.str_content}")
```

## 注意事项

1. **生命周期管理**：必须使用 `async with` 上下文管理器，确保连接正确关闭
2. **多 Server 工具名冲突**：连接多个 Server 时，建议设置 `include_server_name_in_tool_name=True`
3. **超时设置**：根据网络情况调整 `timeout` 参数
4. **错误处理**：工具调用失败不会中断 Agent，而是返回错误信息

## 相关文档

- [MCP Client 实现指南](../../../../examples/MCP_CLIENT_GUIDE.md)
- [Agent 工具系统](../README.md)
