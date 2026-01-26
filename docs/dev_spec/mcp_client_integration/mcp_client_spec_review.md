---
文档标题：mcp_client_spec_review
文档描述：描述 MCP Client 模块的审核目标和测试建议。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [审核目标](#审核目标)
- [功能验证](#功能验证)
- [集成测试](#集成测试)
- [边界测试](#边界测试)
- [性能测试](#性能测试)
- [验收标准](#验收标准)

---

## 审核目标

### 核心目标

1. **功能完整性**：MCP 模块能够正确连接、发现、适配和调用 MCP 工具
2. **接口一致性**：返回的 `ChatCompletionToolParam` 和 `ToolClosure` 符合现有规范
3. **资源管理**：连接能够正确建立和关闭，无泄漏
4. **错误处理**：各类错误能够正确捕获和返回

### 设计约束验证

1. **独立性**：MCP 模块不依赖 ToolFactory 体系
2. **不修改现有代码**：现有文件无需修改即可使用 MCP 模块
3. **配置解耦**：使用独立的 MCP 配置对象

---

## 功能验证

### 1. 连接管理测试

#### 1.1 单 Server 连接

```python
# 测试目标：能够成功连接单个 MCP Server
config = McpClientConfig(
    servers=[
        McpServerConfig(
            url="http://localhost:8000/mcp",
            name="test_server"
        )
    ]
)

async with load_mcp_tools(config) as (tool_params, tool_closures):
    assert len(tool_params) > 0
    assert len(tool_closures) > 0
# 连接应自动关闭
```

#### 1.2 多 Server 连接

```python
# 测试目标：能够同时连接多个 MCP Server
config = McpClientConfig(
    servers=[
        McpServerConfig(url="http://localhost:8000/mcp", name="server1"),
        McpServerConfig(url="http://localhost:8001/mcp", name="server2")
    ]
)

async with load_mcp_tools(config) as (tool_params, tool_closures):
    # 验证两个 Server 的工具都被加载
    server1_tools = [t for t in tool_params if t.function.name.startswith("server1__")]
    server2_tools = [t for t in tool_params if t.function.name.startswith("server2__")]
    assert len(server1_tools) > 0
    assert len(server2_tools) > 0
```

#### 1.3 连接失败处理

```python
# 测试目标：Server 不存在时能够正确报错
config = McpClientConfig(
    servers=[
        McpServerConfig(url="http://localhost:9999/mcp", name="invalid")
    ]
)

try:
    async with load_mcp_tools(config) as loader:
        pass
    assert False, "Should raise exception"
except Exception as e:
    assert "Failed to connect" in str(e) or "refused" in str(e).lower()
```

### 2. 工具发现测试

#### 2.1 工具列表获取

```python
# 测试目标：能够正确获取 MCP Server 提供的工具列表
async with load_mcp_tools(config) as (tool_params, tool_closures):
    # 验证工具参数格式
    for tool_param in tool_params:
        assert tool_param.type == "function"
        assert hasattr(tool_param.function, "name")
        assert hasattr(tool_param.function, "description")
        assert hasattr(tool_param.function, "parameters")

    # 验证工具闭包存在
    for tool_name, closure in tool_closures.items():
        assert callable(closure)
```

#### 2.2 工具名称前缀

```python
# 测试目标：多 Server 场景下工具名称正确添加前缀
config = McpClientConfig(
    servers=[
        McpServerConfig(url="http://localhost:8000/mcp", name="tools"),
        McpServerConfig(url="http://localhost:8001/mcp", name="calc")
    ],
    include_server_name_in_tool_name=True
)

async with load_mcp_tools(config) as (tool_params, tool_closures):
    # 验证工具名前缀
    for name in tool_closures.keys():
        assert name.startswith("tools__") or name.startswith("calc__")
```

### 3. 工具过滤测试

#### 3.1 白名单过滤

```python
# 测试目标：白名单过滤生效
config = McpClientConfig(
    servers=[McpServerConfig(url="http://localhost:8000/mcp", name="test")],
    tool_filter=McpToolFilter(
        allow_list=["tool1", "tool2"]
    )
)

async with load_mcp_tools(config) as (tool_params, tool_closures):
    # 验证只有白名单中的工具被加载
    for name in tool_closures.keys():
        assert name.endswith("__tool1") or name.endswith("__tool2")
```

#### 3.2 黑名单过滤

```python
# 测试目标：黑名单过滤生效
config = McpClientConfig(
    servers=[McpServerConfig(url="http://localhost:8000/mcp", name="test")],
    tool_filter=McpToolFilter(
        deny_list=["tool3"]
    )
)

async with load_mcp_tools(config) as (tool_params, tool_closures):
    # 验证黑名单中的工具未被加载
    for name in tool_closures.keys():
        assert not name.endswith("__tool3")
```

#### 3.3 混合过滤

```python
# 测试目标：白名单优先级高于黑名单
config = McpClientConfig(
    servers=[McpServerConfig(url="http://localhost:8000/mcp", name="test")],
    tool_filter=McpToolFilter(
        allow_list=["tool1", "tool2"],
        deny_list=["tool3"]
    )
)

async with load_mcp_tools(config) as (tool_params, tool_closures):
    # tool3 不在白名单中，即使黑名单包含也不应该出现
    for name in tool_closures.keys():
        assert not name.endswith("__tool3")
```

### 4. 工具调用测试

#### 4.1 成功调用

```python
# 测试目标：工具调用能够成功执行并返回正确结果
async with load_mcp_tools(config) as (tool_params, tool_closures):
    # 假设有一个 calculator 工具
    closure = tool_closures.get("test__calculator")
    if closure:
        result = await closure(a=1, b=2)
        assert result.occur_error == False
        assert result.str_content is not None
```

#### 4.2 参数错误处理

```python
# 测试目标：参数错误时返回错误信息
async with load_mcp_tools(config) as (tool_params, tool_closures):
    closure = tool_closures.get("test__calculator")
    if closure:
        # 传递错误的参数
        result = await closure(invalid_param="test")
        assert result.occur_error == True
        assert "失败" in result.str_content or "error" in result.str_content.lower()
```

#### 4.3 超时处理

```python
# 测试目标：工具调用超时时能够正确处理
config = McpClientConfig(
    servers=[McpServerConfig(
        url="http://localhost:8000/mcp",
        name="test",
        timeout=0.1  # 100ms 超时
    )]
)

async with load_mcp_tools(config) as (tool_params, tool_closures):
    closure = tool_closures.get("test__slow_tool")
    if closure:
        result = await closure()
        assert result.occur_error == True
        assert "timeout" in result.str_content.lower() or "超时" in result.str_content
```

---

## 集成测试

### 与 Agent 集成

```python
# 测试目标：MCP 工具能够被 Agent 正确使用
from api.agent.base_agent import BaseAgent

async def test_agent_integration():
    config = McpClientConfig(
        servers=[McpServerConfig(url="http://localhost:8000/mcp", name="test")]
    )

    async with load_mcp_tools(config) as (tool_params, tool_closures):
        # 创建 Agent
        agent = BaseAgent(
            cancel_event=Event(),
            tools=tool_params,
            tool_call_function=tool_closures
        )

        # 运行 Agent
        # result = await agent.run("使用 calculator 工具计算 1 + 2")
        # 验证结果...
```

---

## 边界测试

### 1. 空 Server 列表

```python
# 测试目标：配置为空时应该报错
config = McpClientConfig(servers=[])

try:
    McpClientConfig.model_validate(config.model_dump())
    assert False, "Should raise validation error"
except ValueError as e:
    assert "至少需要配置一个" in str(e)
```

### 2. 无工具匹配过滤条件

```python
# 测试目标：过滤后无工具时应返回空列表
config = McpClientConfig(
    servers=[McpServerConfig(url="http://localhost:8000/mcp", name="test")],
    tool_filter=McpToolFilter(
        allow_list=["non_existent_tool"]
    )
)

async with load_mcp_tools(config) as (tool_params, tool_closures):
    assert len(tool_params) == 0
    assert len(tool_closures) == 0
```

### 3. 禁用 MCP

```python
# 测试目标：enabled=False 时应该跳过加载
config = McpClientConfig(enabled=True)  # 注意：当前设计可能不支持此功能

# 如果需要支持禁用功能，应在外部调用前检查
if config.enabled:
    async with load_mcp_tools(config) as loader:
        pass
```

---

## 性能测试

### 1. 连接建立时间

```python
# 测试目标：连接建立时间应该在可接受范围内
import time

config = McpClientConfig(
    servers=[McpServerConfig(url="http://localhost:8000/mcp", name="test")]
)

start = time.time()
async with load_mcp_tools(config) as loader:
    pass
duration = time.time() - start

assert duration < 5.0, f"Connection took too long: {duration}s"
```

### 2. 工具调用延迟

```python
# 测试目标：工具调用延迟应该在可接受范围内
async with load_mcp_tools(config) as (tool_params, tool_closures):
    closure = tool_closures.get("test__fast_tool")

    start = time.time()
    result = await closure()
    duration = time.time() - start

    assert duration < 1.0, f"Tool call took too long: {duration}s"
```

---

## 验收标准

### 必须满足

1. ✅ 能够成功连接到 MCP Server
2. ✅ 能够获取并正确解析工具列表
3. ✅ 工具过滤功能正常工作
4. ✅ 工具调用能够成功执行
5. ✅ 错误能够正确捕获并返回 `ToolTaskResult(occur_error=True)`
6. ✅ 连接能够正确关闭（无资源泄漏）
7. ✅ 返回的 `ChatCompletionToolParam` 格式正确
8. ✅ 返回的 `ToolClosure` 能够被 Agent 调用

### 建议满足

1. ⚠️ 支持多 Server 同时连接
2. ⚠️ 工具名称前缀避免冲突
3. ⚠️ 超时机制正常工作
4. ⚠️ 日志记录完善
5. ⚠️ 文档完整清晰

---

## 测试工具建议

### 1. MCP 测试 Server

建议创建一个简单的 MCP 测试 Server，提供以下工具：

```python
# test_mcp_server.py
from mcp.server.fastmcp import FastMCP

server = FastMCP("test_server", json_response=False)

@server.tool()
def calculator(a: float, b: float, operation: str = "add") -> str:
    """简单的计算器工具"""
    if operation == "add":
        return f"{a + b}"
    elif operation == "multiply":
        return f"{a * b}"
    else:
        return "Unknown operation"

@server.tool()
def slow_tool(seconds: float = 1) -> str:
    """慢速工具，用于测试超时"""
    import asyncio
    asyncio.sleep(seconds)
    return f"Waited {seconds} seconds"

@server.tool()
def error_tool() -> str:
    """总是返回错误的工具"""
    raise ValueError("This tool always fails")
```

### 2. 测试脚本

创建一个完整的测试脚本 `test_mcp_client.py`，包含所有上述测试用例。

---

## 测试执行计划

1. **单元测试**：测试每个独立组件
   - `McpServerConnection` 测试
   - `McpToolWrapper` 测试
   - 工具过滤逻辑测试

2. **集成测试**：测试完整流程
   - 单 Server 场景
   - 多 Server 场景
   - 与 Agent 集成

3. **边界测试**：测试异常情况
   - 连接失败
   - 超时
   - 空 Server 列表

4. **性能测试**：验证性能指标
   - 连接建立时间
   - 工具调用延迟
