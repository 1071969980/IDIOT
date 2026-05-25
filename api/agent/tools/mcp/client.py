"""
MCP 客户端连接管理
"""

import asyncio
import logfire
import ujson
from typing import Any
from dataclasses import dataclass

from mcp import ClientSession
from mcp.server.fastmcp.exceptions import FastMCPError
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool as McpTool, CallToolResult

from api.logger.datamodel import LangFuseSpanAttributes

from .config_data_model import McpClientConfig, McpToolFilter


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
    include_server_name_in_tool_name: bool
    tool_filter: McpToolFilter
    explicit: bool

    # 运行时状态
    session: ClientSession | None = None
    read_stream: Any = None
    write_stream: Any = None
    _client_ctx: Any = None
    _is_initialized: bool = False
    init_result: Any = None  # 保存初始化结果，包含服务器信息

    async def __aenter__(self):
        """建立连接并初始化会话"""
        try:
            # 建立 Streamable-HTTP 连接
            self._client_ctx = streamable_http_client(
                self.url
            )
            self.read_stream, self.write_stream, self.get_session_id = \
                await self._client_ctx.__aenter__()

            # 创建会话
            self.session = ClientSession(self.read_stream, self.write_stream, logging_callback=self.log_clouser())
            await self.session.__aenter__()

            # 初始化
            self.init_result = await self.session.initialize()
            self._is_initialized = True
            
            return self

        except Exception as e:
            print(e)
            import traceback
            traceback.print_exc()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭连接"""
        try:
            if self.session:
                await self.session.__aexit__(exc_type, exc_val, exc_tb)
            if self._client_ctx:
                await self._client_ctx.__aexit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            pass
        
    def log_clouser(self):
        from mcp.types import LoggingMessageNotificationParams
        async def clouser(params: LoggingMessageNotificationParams) -> None:
            # prepare data
            try:
                log_data = params.data if isinstance(params.data, str) else ujson.dumps(params.data, ensure_ascii=False)
            except Exception:
                logfire.warn("MCP::Failed to dumps tool log data")
                return
            
            # prepare metadate
            LF_span_attributes = LangFuseSpanAttributes(
                metadata={
                    "mcp_server_name": self.server_name,
                    "mcp_server_url": self.url
                }
            )  # type: ignore
            
            # log
            match params.level:
                case "debug":
                    logfire.debug(log_data,
                                  mcp_log_data=log_data,
                                  **LF_span_attributes.model_dump(mode="json", by_alias=True, exclude_none=True))
                case "info":
                    logfire.info(log_data,
                                 mcp_log_data=log_data,
                                 **LF_span_attributes.model_dump(mode="json", by_alias=True, exclude_none=True))
                case "warning" | "notice":
                    logfire.warn(log_data,
                                 mcp_log_data=log_data,
                                 **LF_span_attributes.model_dump(mode="json", by_alias=True, exclude_none=True))
                case _:
                    logfire.error(log_data,
                                  mcp_log_data=log_data,
                                  **LF_span_attributes.model_dump(mode="json", by_alias=True, exclude_none=True))
            
        return clouser

    async def list_tools(self) -> list[McpTool]:
        """获取可用工具列表"""
        if not self._is_initialized:
            raise RuntimeError(f"MCP Server '{self.server_name}' not initialized")
        if self.session is None:
            raise RuntimeError(f"MCP Server '{self.server_name}' initialized but session connection is None")
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
            if self.session is None:
                raise RuntimeError(f"MCP Server '{self.server_name}' initialized but session connection is None")
            meta = arguments.pop("metadata", None)
            result = await self.session.call_tool(name, arguments, meta=meta)
            return result
        except FastMCPError as e:
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
            if not server_config.enabled:
                continue
            conn = McpServerConnection(
                server_name=server_config.name,
                url=server_config.url,
                timeout=server_config.timeout,
                json_response=server_config.json_response,
                include_server_name_in_tool_name=server_config.include_server_name_in_tool_name,
                tool_filter=server_config.tool_filter,
                explicit=server_config.explicit,
            )
            await conn.__aenter__()
            self.connections.append(conn)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭所有连接"""
        for conn in self.connections:
            await conn.__aexit__(exc_type, exc_val, exc_tb)
        self.connections.clear()

    async def get_all_tools(self) -> dict[str, list[tuple[McpTool, McpServerConnection]]]:
        """
        获取所有可用的工具

        Returns:
            {server_name: [(tool_info, connection), ...]}
        """
        all_tools: dict[str, list[tuple[McpTool, McpServerConnection]]] = {}

        for conn in self.connections:
            all_tools[conn.server_name] = []
            tools = await conn.list_tools()
            for tool in tools:
                all_tools[conn.server_name].append((tool, conn))

        return all_tools
