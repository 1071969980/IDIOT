---
文档标题：mcp_client_spec_implementation
文档描述：从软件工程的角度，描述 MCP Client 模块的实现细节，包括文件夹结构、关键代码片段等。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [文件夹结构](#文件夹结构)
- [配置数据模型](#配置数据模型)
- [连接管理](#连接管理)
- [工具映射](#工具映射)
- [主适配器](#主适配器)
- [模块导出](#模块导出)
- [实现顺序](#实现顺序)

---

## 文件夹结构

```
api/agent/tools/mcp/
├── __init__.py                      # 模块导出
├── config_data_model.py             # 配置数据模型
├── client.py                        # 连接管理
├── tool_mapper.py                   # 工具映射
├── adapter.py                       # 主适配器
└── README.md                        # 使用文档
```

---

## 配置数据模型

### 文件：`config_data_model.py`

```python
"""
MCP Client 配置数据模型
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator

# 导入项目的基础配置类
from api.agent.tools.config_data_model import SessionToolConfigBase


class McpServerConfig(BaseModel):
    """
    单个 MCP Server 配置

    Attributes:
        url: MCP Server 的 streamable HTTP URL
        name: Server 名称，用于日志和工具名称前缀
        timeout: 连接和调用超时时间（秒）
    """
    url: str = Field(
        description="MCP Server 的 streamable HTTP URL (例如: http://localhost:8000/mcp)"
    )
    name: str = Field(
        default="default",
        description="Server 名称，用于日志和错误信息"
    )
    timeout: float = Field(
        default=30.0,
        description="连接和调用超时时间（秒）"
    )


class McpToolFilter(BaseModel):
    """
    MCP 工具过滤配置

    Attributes:
        allow_list: 允许的工具名称列表（白名单），为空则允许所有工具
        deny_list: 禁止的工具名称列表（黑名单）
    """
    allow_list: list[str] | None = Field(
        default=None,
        description="允许的工具名称列表（白名单），为空则允许所有工具"
    )
    deny_list: list[str] = Field(
        default_factory=list,
        description="禁止的工具名称列表（黑名单）"
    )


class McpClientConfig(BaseModel):
    """
    MCP Client 工具配置

    支持连接多个 MCP Server，并过滤可用工具。

    Attributes:
        enabled: 是否启用 MCP Client
        servers: 要连接的 MCP Server 列表
        tool_filter: 工具过滤配置
        include_server_name_in_tool_name: 是否在工具名称前添加 server 前缀
        json_response: MCP 响应模式（SSE 或 JSON）
    """
    enabled: bool = True

    servers: list[McpServerConfig] = Field(
        default_factory=list,
        description="要连接的 MCP Server 列表"
    )

    tool_filter: McpToolFilter = Field(
        default_factory=McpToolFilter,
        description="工具过滤配置"
    )

    include_server_name_in_tool_name: bool = Field(
        default=True,
        description=(
            "是否在工具名称前添加 server 前缀。"
            "如果连接多个 server，建议设置为 True 以避免工具名冲突。"
        )
    )

    json_response: bool = Field(
        default=False,
        description=(
            "MCP 响应模式。"
            "False 使用 SSE 模式（支持日志和进度通知）；"
            "True 使用 JSON 模式（仅返回最终结果）。"
        )
    )

    @field_validator("servers")
    @classmethod
    def validate_servers(cls, v: list[McpServerConfig]) -> list[McpServerConfig]:
        if not v:
            raise ValueError("至少需要配置一个 MCP Server")
        return v
```

---

## 连接管理

### 文件：`client.py`

```python
"""
MCP 客户端连接管理
"""

import asyncio
from typing import Any
from dataclasses import dataclass

from mcp import ClientSession, ClientError
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool as McpTool, CallToolResult

from api.logger import logger
from .config_data_model import McpClientConfig


@dataclass
class McpServerConnection:
    """
    MCP Server 连接封装

    管理 streamable_http_client 和 ClientSession 的生命周期。
    """
    server_name: str
    url: str
    timeout: float
    json_response: bool

    # 运行时状态
    session: ClientSession | None = None
    read_stream: Any = None
    write_stream: Any = None
    _client_ctx: Any = None
    _is_initialized: bool = False

    async def __aenter__(self):
        """建立连接并初始化会话"""
        try:
            # 建立 Streamable-HTTP 连接
            self._client_ctx = streamable_http_client(
                self.url,
                timeout=self.timeout
            )
            self.read_stream, self.write_stream, self.get_session_id = \
                await self._client_ctx.__aenter__()

            # 创建会话
            self.session = ClientSession(self.read_stream, self.write_stream)
            await self.session.__aenter__()

            # 初始化
            init_result = await self.session.initialize()
            self._is_initialized = True

            logger.info(f"MCP Server '{self.server_name}' connected: {init_result.serverInfo.name}")
            return self

        except Exception as e:
            logger.error(f"Failed to connect to MCP Server '{self.server_name}': {e}")
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭连接"""
        try:
            if self.session:
                await self.session.__aexit__(exc_type, exc_val, exc_tb)
            if self._client_ctx:
                await self._client_ctx.__aexit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            logger.error(f"Error closing MCP Server '{self.server_name}': {e}")

    async def list_tools(self) -> list[McpTool]:
        """获取可用工具列表"""
        if not self._is_initialized:
            raise RuntimeError(f"MCP Server '{self.server_name}' not initialized")

        result = await self.session.list_tools()
        return result.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any]
    ) -> CallToolResult:
        """调用工具"""
        if not self._is_initialized:
            raise RuntimeError(f"MCP Server '{self.server_name}' not initialized")

        try:
            result = await self.session.call_tool(name, arguments)
            return result
        except ClientError as e:
            logger.error(f"MCP tool call failed: {name} - {e}")
            raise


class McpClientManager:
    """
    MCP 客户端管理器

    管理 MCP Server 连接的生命周期，确保 Per-Agent-Run 模式。
    """

    def __init__(self, config: McpClientConfig):
        self.config = config
        self.connections: list[McpServerConnection] = []

    async def __aenter__(self):
        """建立所有 Server 连接"""
        for server_config in self.config.servers:
            conn = McpServerConnection(
                server_name=server_config.name,
                url=server_config.url,
                timeout=server_config.timeout,
                json_response=server_config.json_response
            )
            await conn.__aenter__()
            self.connections.append(conn)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭所有连接"""
        for conn in self.connections:
            await conn.__aexit__(exc_type, exc_val, exc_tb)
        self.connections.clear()

    async def get_all_tools(self) -> dict[str, tuple[McpTool, McpServerConnection]]:
        """
        获取所有可用的工具

        Returns:
            {tool_name: (tool_info, connection)}
        """
        all_tools = {}

        for conn in self.connections:
            tools = await conn.list_tools()
            for tool in tools:
                all_tools[tool.name] = (tool, conn)

        return all_tools
```

---

## 工具映射

### 文件：`tool_mapper.py`

```python
"""
MCP 工具映射到 Agent 工具
"""

from typing import Any

from mcp.types import Tool as McpTool, CallToolResult
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from api.agent.tools.type import ToolTaskResult
from .client import McpServerConnection
from .config_data_model import McpToolFilter


def should_include_tool(tool_name: str, filter_config: McpToolFilter) -> bool:
    """
    根据过滤配置判断是否包含工具

    Args:
        tool_name: 工具名称
        filter_config: 过滤配置

    Returns:
        True 如果工具应该被包含
    """
    # 检查黑名单
    if tool_name in filter_config.deny_list:
        return False

    # 检查白名单
    if filter_config.allow_list is not None:
        return tool_name in filter_config.allow_list

    # 默认包含
    return True


class McpToolWrapper:
    """
    MCP 工具包装器

    将 MCP 工具调用转换为 ToolClosure，并处理结果转换。
    """

    def __init__(
        self,
        mcp_tool: McpTool,
        connection: McpServerConnection,
        tool_name_prefix: str = ""
    ):
        self.mcp_tool = mcp_tool
        self.connection = connection
        self.tool_name_prefix = tool_name_prefix

    def get_tool_param(self) -> ChatCompletionToolParam:
        """生成 OpenAI 工具参数"""
        full_name = f"{self.tool_name_prefix}{self.mcp_tool.name}" \
            if self.tool_name_prefix else self.mcp_tool.name

        return ChatCompletionToolParam(
            type="function",
            function=FunctionDefinition(
                name=full_name,
                description=self.mcp_tool.description or "",
                parameters=self._convert_input_schema()
            )
        )

    def _convert_input_schema(self) -> dict:
        """
        转换 MCP inputSchema 为 OpenAI 格式

        MCP 的 inputSchema 已经是 JSON Schema 格式，
        只需移除一些 OpenAI 不支持的字段。
        """
        schema = dict(self.mcp_tool.inputSchema)

        # 移除 OpenAI 不支持的字段
        schema.pop("$schema", None)
        schema.pop("$id", None)

        return schema

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        执行工具调用

        Args:
            **kwargs: LLM 传递的参数

        Returns:
            ToolTaskResult: 执行结果
        """
        try:
            result = await self.connection.call_tool(
                self.mcp_tool.name,
                kwargs
            )

            return self._convert_result(result)

        except Exception as e:
            return ToolTaskResult(
                str_content=f"MCP 工具调用失败 ({self.mcp_tool.name}): {str(e)}",
                occur_error=True
            )

    def _convert_result(self, mcp_result: CallToolResult) -> ToolTaskResult:
        """
        转换 MCP 结果为 ToolTaskResult

        Args:
            mcp_result: MCP 返回的结果

        Returns:
            ToolTaskResult: 转换后的结果
        """
        content_parts = []

        for content_item in mcp_result.content:
            if hasattr(content_item, "text"):
                content_parts.append(content_item.text)
            elif hasattr(content_item, "data"):
                # 处理二进制数据（如图片）
                content_parts.append(f"[Binary data: {len(content_item.data)} bytes]")
            else:
                content_parts.append(str(content_item))

        str_content = "\n".join(content_parts)

        # 检查是否有错误
        is_error = any(
            hasattr(item, "type") and item.type == "error"
            for item in mcp_result.content
        )

        return ToolTaskResult(
            str_content=str_content,
            json_content={"raw_response": mcp_result.model_dump()} if str_content else None,
            occur_error=is_error
        )
```

---

## 主适配器

### 文件：`adapter.py`

```python
"""
MCP Client 主适配器

提供对外 API，将 MCP 工具转换为 Agent 可用的工具列表。
"""

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure
from .config_data_model import McpClientConfig
from .client import McpClientManager
from .tool_mapper import McpToolWrapper, should_include_tool


class McpToolsLoader:
    """
    MCP 工具加载器

    使用上下文管理器确保连接正确关闭。
    """

    def __init__(self, config: McpClientConfig):
        self.config = config
        self.manager: McpClientManager | None = None
        self._tool_params: list[ChatCompletionToolParam] | None = None
        self._tool_closures: dict[str, ToolClosure] | None = None

    async def __aenter__(self):
        """建立连接并加载工具"""
        self.manager = McpClientManager(self.config)
        await self.manager.__aenter__()

        # 获取所有工具
        all_tools = await self.manager.get_all_tools()

        # 构建工具列表
        tool_params = []
        tool_closures = {}

        for mcp_tool_name, (mcp_tool, connection) in all_tools.items():
            # 应用过滤
            if not should_include_tool(mcp_tool_name, self.config.tool_filter):
                continue

            # 创建工具包装器
            prefix = f"{connection.server_name}__" \
                if self.config.include_server_name_in_tool_name else ""

            wrapper = McpToolWrapper(
                mcp_tool=mcp_tool,
                connection=connection,
                tool_name_prefix=prefix
            )

            # 获取工具参数
            tool_param = wrapper.get_tool_param()
            tool_params.append(tool_param)

            # 注册闭包
            tool_closures[tool_param.function.name] = wrapper

        self._tool_params = tool_params
        self._tool_closures = tool_closures

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭连接"""
        if self.manager:
            await self.manager.__aexit__(exc_type, exc_val, exc_tb)

    @property
    def tool_params(self) -> list[ChatCompletionToolParam]:
        """获取工具参数列表"""
        if self._tool_params is None:
            raise RuntimeError("Tools not loaded. Use async with context manager.")
        return self._tool_params

    @property
    def tool_closures(self) -> dict[str, ToolClosure]:
        """获取工具闭包字典"""
        if self._tool_closures is None:
            raise RuntimeError("Tools not loaded. Use async with context manager.")
        return self._tool_closures

    def get_tools(self) -> tuple[list[ChatCompletionToolParam], dict[str, ToolClosure]]:
        """
        获取工具列表

        Returns:
            (tool_params, tool_closures)
        """
        return self.tool_params, self.tool_closures


async def load_mcp_tools(config: McpClientConfig):
    """
    加载 MCP 工具的主入口函数

    Args:
        config: MCP Client 配置

    Returns:
        McpToolsLoader 实例，需要使用 async with 进入上下文

    Example:
        >>> async with load_mcp_tools(config) as loader:
        ...     tool_params, tool_closures = loader.get_tools()
        ...     # 使用工具...
    """
    return McpToolsLoader(config)
```

---

## 模块导出

### 文件：`__init__.py`

```python
"""
MCP Client 模块

提供 MCP Server 工具到 Agent 的桥接功能。
"""

from .config_data_model import (
    McpServerConfig,
    McpToolFilter,
    McpClientConfig
)
from .adapter import load_mcp_tools, McpToolsLoader

__all__ = [
    "McpServerConfig",
    "McpToolFilter",
    "McpClientConfig",
    "load_mcp_tools",
    "McpToolsLoader"
]
```

---

## 实现顺序

1. **`config_data_model.py`**（无依赖）
   - 定义配置类
   - 添加数据验证

2. **`client.py`**（依赖 config_data_model）
   - 实现 McpServerConnection
   - 实现 McpClientManager

3. **`tool_mapper.py`**（依赖 client）
   - 实现 should_include_tool
   - 实现 McpToolWrapper

4. **`adapter.py`**（依赖上述所有）
   - 实现 McpToolsLoader
   - 实现 load_mcp_tools

5. **`__init__.py`**（依赖上述所有）
   - 导出公共 API

6. **`README.md`**（文档）
   - 使用说明
   - 配置示例
