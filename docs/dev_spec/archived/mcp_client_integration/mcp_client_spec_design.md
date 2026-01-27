---
文档标题：mcp_client_spec_design
文档描述：描述 MCP Client 模块的需求、概念层面的设计结构和自然语言表达的执行逻辑。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [需求描述](#需求描述)
- [核心概念](#核心概念)
- [架构设计](#架构设计)
- [执行逻辑](#执行逻辑)
- [错误处理](#错误处理)
- [工具过滤机制](#工具过滤机制)

---

## 需求描述

### 功能需求

开发一个独立的 MCP Client 模块，实现以下功能：

1. **连接管理**：连接到一个或多个 MCP Server
2. **工具发现**：获取 MCP Server 提供的工具列表
3. **工具过滤**：根据配置过滤可用工具
4. **工具适配**：将 MCP 工具转换为 ToolClosure
5. **结果转换**：将 MCP 调用结果转换为 ToolTaskResult

### 非功能需求

1. **生命周期**：Per-Agent-Run，每次使用时创建连接，执行完毕后关闭
2. **解耦设计**：与现有 ToolFactory 体系完全解耦
3. **错误处理**：调用失败时返回包含错误信息的 ToolTaskResult
4. **资源管理**：确保连接正确关闭

### 设计约束

1. **不修改现有代码**：不修改 ToolFactory、chat_task.py 等现有文件
2. **独立配置**：使用独立的 MCP 配置对象

---

## 核心概念

### MCP 模块定位

MCP 模块是**独立的 ToolClosure 生产者**，与现有的 ToolFactory 体系并行：

```
                    ToolClosure 生产者
                         │
         ┌───────────────┴───────────────┐
         │                               │
    ToolFactory 体系              MCP Client 模块
    (现有系统)                     (本次开发)
```

### Per-Agent-Run 生命周期

```
Agent 运行开始
    │
    ▼
创建 MCP 连接
    │
    ▼
获取工具列表
    │
    ▼
Agent 使用工具
    │
    ▼
Agent 运行结束
    │
    ▼
关闭 MCP 连接
```

### 工具名称前缀

当连接多个 MCP Server 时，为避免工具名冲突，使用前缀：

```
Server "my_tools" 的工具 "search"  →  "my_tools__search"
Server "calc" 的工具 "add"         →  "calc__add"
```

---

## 架构设计

### 模块结构

```
api/agent/tools/mcp/
├── __init__.py                      # 模块导出
├── config_data_model.py             # 配置数据模型
├── client.py                        # 连接管理
├── tool_mapper.py                   # 工具映射
├── adapter.py                       # 主适配器
└── README.md                        # 使用文档
```

### 核心组件

#### 1. 配置模型 (config_data_model.py)

```python
class McpServerConfig:
    """单个 MCP Server 配置"""
    url: str                    # MCP Server URL
    name: str                   # Server 名称（用于工具前缀）
    timeout: float              # 连接超时

class McpToolFilter:
    """工具过滤配置"""
    allow_list: list[str] | None    # 白名单
    deny_list: list[str]            # 黑名单

class McpClientConfig:
    """MCP Client 总配置"""
    servers: list[McpServerConfig]      # Server 列表
    tool_filter: McpToolFilter          # 过滤配置
    include_server_name_in_tool_name: bool  # 是否添加工具前缀
```

#### 2. 连接管理 (client.py)

```python
class McpServerConnection:
    """单个 MCP Server 连接封装"""
    - 管理 streamable_http_client 和 ClientSession
    - 提供 list_tools() 和 call_tool() 方法
    - 使用 async with 管理生命周期

class McpClientManager:
    """多 Server 连接管理器"""
    - 管理多个 McpServerConnection
    - 提供 get_all_tools() 获取所有 Server 的工具
    - 使用 async with 管理所有连接的生命周期
```

#### 3. 工具映射 (tool_mapper.py)

```python
class McpToolWrapper:
    """MCP 工具包装器（实现 ToolClosure 接口）"""
    - 持有 MCP 工具信息和连接引用
    - 实现 __call__(**kwargs) -> ToolTaskResult
    - 处理结果转换
```

#### 4. 主适配器 (adapter.py)

```python
async def load_mcp_tools(config: McpClientConfig):
    """
    主入口函数

    Returns:
        (tool_params, tool_closures)
        - tool_params: list[ChatCompletionToolParam]
        - tool_closures: dict[str, ToolClosure]
    """
```

---

## 执行逻辑

### 主流程

```
load_mcp_tools(config)
    │
    ▼
1. 创建 McpClientManager
    │
    ▼
2. 进入上下文管理器 (async with)
    │   ├─► 连接每个 MCP Server
    │   └─► 初始化 ClientSession
    │
    ▼
3. 获取所有 Server 的工具列表
    │
    ▼
4. 应用工具过滤规则
    │   ├─► 检查黑名单
    │   └─► 检查白名单
    │
    ▼
5. 为每个工具创建 McpToolWrapper
    │   ├─► 生成 ChatCompletionToolParam
    │   └─► 注册 ToolClosure
    │
    ▼
6. 返回 (tool_params, tool_closures)
    │
    ▼
7. 退出上下文管理器
    └─► 关闭所有连接
```

### 工具调用流程

```
Agent 调用工具
    │
    ▼
McpToolWrapper.__call__(**kwargs)
    │
    ▼
1. 参数验证（可选）
    │
    ▼
2. 调用 connection.call_tool(name, arguments)
    │
    ▼
3. 等待 MCP Server 返回
    │
    ▼
4. 转换结果为 ToolTaskResult
    │   ├─► 提取 text 内容
    │   ├─► 处理二进制数据
    │   └─► 检查错误标志
    │
    ▼
5. 返回 ToolTaskResult
```

---

## 错误处理

### 连接错误

- **策略**：在 `McpClientManager.__aenter__` 中捕获
- **处理**：记录日志，抛出异常，终止整个工具加载过程
- **原因**：无法连接 Server 时无法继续

### 工具调用错误

- **策略**：在 `McpToolWrapper.__call__` 中捕获
- **处理**：返回 `ToolTaskResult(occur_error=True, str_content=error_message)`
- **原因**：单个工具失败不应影响其他工具

### 超时处理

- **策略**：使用 `asyncio.wait_for` 包装调用
- **处理**：超时后返回错误信息
- **配置**：通过 `McpServerConfig.timeout` 设置

---

## 工具过滤机制

### 过滤优先级

```
1. 检查黑名单 (deny_list)
   ├─► 在黑名单 → 排除
   └─► 不在黑名单 → 继续

2. 检查白名单 (allow_list)
   ├─► 白名单为 None → 包含
   ├─► 在白名单中 → 包含
   └─► 不在白名单中 → 排除
```

### 使用场景

| 场景 | allow_list | deny_list | 结果 |
|------|-----------|-----------|------|
| 允许所有工具 | `None` | `[]` | 所有工具 |
| 仅允许特定工具 | `["tool1", "tool2"]` | `[]` | 仅 tool1, tool2 |
| 排除特定工具 | `None` | `["tool3"]` | 除 tool3 外的所有 |
| 混合模式 | `["tool1", "tool2"]` | `["tool3"]` | 仅 tool1, tool2（tool3 不在白名单中） |

---

## 外部 API 设计

### 使用方式

```python
from api.agent.tools.mcp import load_mcp_tools, McpClientConfig, McpServerConfig

# 1. 配置
config = McpClientConfig(
    servers=[
        McpServerConfig(
            url="http://localhost:8000/mcp",
            name="my_tools",
            timeout=30.0
        )
    ],
    tool_filter=McpToolFilter(
        allow_list=["search", "calculator"]
    ),
    include_server_name_in_tool_name=True
)

# 2. 加载工具
async with load_mcp_tools(config) as (tool_params, tool_closures):
    # tool_params: list[ChatCompletionToolParam]
    # tool_closures: dict[str, ToolClosure]

    # 3. 传入 Agent
    agent = BaseAgent(
        tools=tool_params,
        tool_call_function=tool_closures,
        ...
    )

    # 4. 运行 Agent
    await agent.run()

# 5. 连接自动关闭
```

### 非 Context Manager 方式（不推荐）

```python
manager = McpClientManager(config)
await manager.__aenter__()
try:
    tool_params, tool_closures = await manager.get_tools()
    # 使用工具...
finally:
    await manager.__aexit__(None, None, None)
```
