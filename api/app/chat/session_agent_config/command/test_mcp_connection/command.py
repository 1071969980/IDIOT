"""
MCP 连接测试命令实现
"""

import asyncio
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..base import AbstractCommand
from .data_model import (
    TestMcpConnectionInput,
    TestMcpConnectionOutput,
    TestModeEnum,
    McpServerTestResult,
    ConnectionStatusEnum,
    ServerInfo,
    ToolInfo,
)

from api.agent.session_agent_config.config_data_model import SessionAgentConfig
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    get_session_config_by_session_id,
)
from api.agent.tools.mcp.client import McpServerConnection
from api.agent.tools.mcp.config_data_model import McpServerConfig


class TestMcpConnectionCommand(AbstractCommand[TestMcpConnectionInput, TestMcpConnectionOutput]):
    """测试 MCP 连接命令"""

    def __init__(self, input_model: TestMcpConnectionInput):
        super().__init__(input_model)
        self._session_uuid: Optional[UUID] = None

    async def execute(self) -> TestMcpConnectionOutput:
        """执行测试连接"""
        # 1. 验证 session_id 格式
        try:
            self._session_uuid = UUID(self.input_model.session_id)
        except ValueError:
            return TestMcpConnectionOutput(
                session_id=self.input_model.session_id,
                success=False,
                message="Invalid session_id format"
            )

        # 2. 加载会话配置
        config = await self._load_config()
        if config.mcp_config is None or not config.mcp_config.servers:
            return TestMcpConnectionOutput(
                session_id=self.input_model.session_id,
                success=True,
                message="No MCP servers configured for this session"
            )

        # 3. 确定要测试的服务器列表
        servers_to_test = self._get_servers_to_test(config.mcp_config.servers)

        if not servers_to_test:
            return TestMcpConnectionOutput(
                session_id=self.input_model.session_id,
                success=False,
                message=f"Server '{self.input_model.server_name}' not found in configuration"
            )

        # 4. 并行测试所有服务器
        results = await self._test_servers_parallel(servers_to_test)

        # 5. 构建输出
        success_count = sum(1 for r in results if r.status == ConnectionStatusEnum.SUCCESS)
        failed_count = len(results) - success_count

        return TestMcpConnectionOutput(
            session_id=self.input_model.session_id,
            results=results,
            total_servers=len(results),
            success_count=success_count,
            failed_count=failed_count,
            success=True,
            message=f"Tested {len(results)} server(s): {success_count} success, {failed_count} failed"
        )

    async def rollback(self) -> TestMcpConnectionOutput:
        """测试命令不需要回滚"""
        return TestMcpConnectionOutput(
            session_id=self.input_model.session_id,
            success=True,
            message="Test MCP connection command doesn't need rollback"
        )

    async def _load_config(self) -> SessionAgentConfig:
        """从数据库加载配置"""
        if self._session_uuid is None:
            return SessionAgentConfig()

        config_data = await get_session_config_by_session_id(self._session_uuid)

        if config_data:
            return SessionAgentConfig.model_validate(config_data.config)
        else:
            return SessionAgentConfig()

    def _get_servers_to_test(self, all_servers: list[McpServerConfig]) -> list[McpServerConfig]:
        """根据测试模式确定要测试的服务器列表"""
        if self.input_model.mode == TestModeEnum.SINGLE:
            if self.input_model.server_name:
                matching = [s for s in all_servers if s.name == self.input_model.server_name]
                return matching
            return []
        else:
            # ALL 模式，测试所有服务器
            return all_servers

    async def _test_servers_parallel(self, servers: list[McpServerConfig]) -> list[McpServerTestResult]:
        """并行测试多个服务器"""
        tasks = [self._test_single_server(server) for server in servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理可能的异常结果
        processed_results: list[McpServerTestResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(McpServerTestResult(
                    server_name=servers[i].name,
                    server_url=servers[i].url,
                    status=ConnectionStatusEnum.FAILED,
                    error_message=str(result),
                    error_type=type(result).__name__,
                    tested_at=datetime.now()
                ))
            else:
                processed_results.append(result)

        return processed_results

    async def _test_single_server(self, server_config: McpServerConfig) -> McpServerTestResult:
        """测试单个 MCP 服务器"""
        start_time = time.time()

        try:
            # 创建连接并测试
            async with McpServerConnection(
                server_name=server_config.name,
                url=server_config.url,
                timeout=server_config.timeout,
                json_response=False,
                tool_filter=server_config.tool_filter,
            ) as conn:
                # 连接成功，获取服务器信息
                server_info = None
                if conn.init_result:
                    init_result = conn.init_result
                    server_name = None
                    protocol_version = None

                    if hasattr(init_result, 'serverInfo') and init_result.serverInfo:
                        server_name = getattr(init_result.serverInfo, 'name', None)
                    if hasattr(init_result, 'protocolVersion'):
                        protocol_version = init_result.protocolVersion

                    server_info = ServerInfo(
                        name=server_name or server_config.name,
                        protocol_version=protocol_version
                    )

                # 获取工具列表
                tools = await conn.list_tools()
                tool_infos = [
                    ToolInfo(
                        name=tool.name,
                        description=tool.description,
                        input_schema=dict(tool.inputSchema) if tool.inputSchema else None
                    )
                    for tool in tools
                ]

                response_time = (time.time() - start_time) * 1000

                return McpServerTestResult(
                    server_name=server_config.name,
                    server_url=server_config.url,
                    status=ConnectionStatusEnum.SUCCESS,
                    server_info=server_info,
                    tools=tool_infos,
                    tool_count=len(tool_infos),
                    response_time_ms=round(response_time, 2),
                    tested_at=datetime.now()
                )

        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return McpServerTestResult(
                server_name=server_config.name,
                server_url=server_config.url,
                status=ConnectionStatusEnum.TIMEOUT,
                error_message=f"Connection timed out after {server_config.timeout} seconds",
                error_type="TimeoutError",
                response_time_ms=round(response_time, 2),
                tested_at=datetime.now()
            )

        except ConnectionError as e:
            response_time = (time.time() - start_time) * 1000
            return McpServerTestResult(
                server_name=server_config.name,
                server_url=server_config.url,
                status=ConnectionStatusEnum.NETWORK_ERROR,
                error_message=str(e),
                error_type="ConnectionError",
                response_time_ms=round(response_time, 2),
                tested_at=datetime.now()
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return McpServerTestResult(
                server_name=server_config.name,
                server_url=server_config.url,
                status=ConnectionStatusEnum.FAILED,
                error_message=str(e),
                error_type=type(e).__name__,
                response_time_ms=round(response_time, 2),
                tested_at=datetime.now()
            )