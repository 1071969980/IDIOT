import time
from datetime import datetime, timezone
from uuid import UUID

from ..base import AbstractCommand
from .data_model import (
    TestMcpConnectionInput,
    TestMcpConnectionOutput,
    McpServerTestResult,
    McpToolInfo,
    ServerInfo,
)
from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
)
from api.agent.tools.mcp.client import McpServerConnection
from api.agent.tools.mcp.config_data_model import McpServerConfig
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    get_or_create_pending_task,
)
from api.chat.sql_stat.u2a_session_task.utils import get_task


async def _test_single_server(server_config: McpServerConfig) -> McpServerTestResult:
    """测试单个 MCP 服务器并返回结果。"""
    start_time = time.time()
    tested_at = datetime.now(timezone.utc)

    try:
        async with McpServerConnection(
            server_name=server_config.name,
            url=server_config.url,
            timeout=server_config.timeout,
            json_response=server_config.json_response,
            tool_filter=server_config.tool_filter,
            include_server_name_in_tool_name=server_config.include_server_name_in_tool_name,
        ) as conn:
            # 提取服务器信息
            server_info = None
            if conn.init_result:
                init_result = conn.init_result
                s_name = (
                    getattr(init_result.serverInfo, 'name', None)
                    if hasattr(init_result, 'serverInfo') and init_result.serverInfo
                    else None
                )
                proto_ver = (
                    getattr(init_result, 'protocolVersion', None)
                    if hasattr(init_result, 'protocolVersion')
                    else None
                )
                server_info = ServerInfo(
                    name=s_name or server_config.name,
                    protocol_version=proto_ver,
                )

            # 获取工具列表
            tools = await conn.list_tools()
            tool_infos = [
                McpToolInfo(
                    name=t.name,
                    description=t.description,
                    input_schema=dict(t.inputSchema) if t.inputSchema else None,
                )
                for t in tools
            ]

            response_time = (time.time() - start_time) * 1000

            return McpServerTestResult(
                server_name=server_config.name,
                server_url=server_config.url,
                status="success",
                server_info=server_info,
                tools=tool_infos,
                tool_count=len(tool_infos),
                response_time_ms=round(response_time, 2),
                tested_at=tested_at,
            )

    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return McpServerTestResult(
            server_name=server_config.name,
            server_url=server_config.url,
            status="failed",
            error_message=str(e),
            error_type=type(e).__name__,
            response_time_ms=round(response_time, 2),
            tested_at=tested_at,
        )


class TestMcpConnectionCommand(
    AbstractCommand[TestMcpConnectionInput, TestMcpConnectionOutput]
):

    async def execute(self) -> TestMcpConnectionOutput:
        session_uuid = UUID(self.session_id)
        base_config = await get_base_session_config(session_uuid)

        branch_name = self.input_model.branch_name
        if branch_name is not None:
            task_id, _ = await get_or_create_pending_task(
                session_id=session_uuid,
                user_id=UUID(self.user_id),
                branch_name=branch_name,
            )
            task = await get_task(task_id)
            effective_config = get_effective_session_config(
                base_config,
                storage_snapshot=dict(task.storage_snapshot) if task and task.storage_snapshot else None,
            )
        else:
            effective_config = base_config

        # 无 MCP 配置
        if effective_config.mcp_config is None or not effective_config.mcp_config.servers:
            return TestMcpConnectionOutput(results=[])

        all_servers = effective_config.mcp_config.servers

        # 确定要测试的服务器
        if self.input_model.mode == "single":
            if not self.input_model.server_name:
                raise ValueError("server_name is required when mode='single'")

            target = None
            for s in all_servers:
                if s.name == self.input_model.server_name:
                    target = s
                    break
            if target is None:
                raise ValueError(
                    f"Server '{self.input_model.server_name}' not found. "
                    f"Available: {[s.name for s in all_servers]}"
                )
            servers_to_test = [target]
        else:
            servers_to_test = list(all_servers)

        # 测试所有目标服务器
        results = []
        for server in servers_to_test:
            result = await _test_single_server(server)
            results.append(result)

        success_count = sum(1 for r in results if r.status == "success")
        failed_count = len(results) - success_count

        return TestMcpConnectionOutput(
            results=results,
            total_servers=len(results),
            success_count=success_count,
            failed_count=failed_count,
        )
