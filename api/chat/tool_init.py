from typing import TYPE_CHECKING, Any
from uuid import UUID

from api.agent.tools.tool_factory import ToolFactory, UserToolCallingPermissionRole
from api.agent.tools.mcp.adapter import load_mcp_tools
from api.agent.session_agent_config.config_data_model import SessionAgentConfig

from api.chat.data_model import ToolInitializationResult

from api.agent.tools.mcp.adapter import McpToolsLoader


class _EmptyAsyncContextManager:
    """异步空上下文管理器，用于不需要 MCP 工具时"""
    async def __aenter__(self) -> None:
        return None
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

async def init_tools(
        user_id_for_scope: UUID,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        branch_name: str,
        session_config: SessionAgentConfig,
        user_permission_role: UserToolCallingPermissionRole,
        **kwargs: Any,
) -> tuple[ToolInitializationResult, _EmptyAsyncContextManager | McpToolsLoader]:
    
    tools_config = session_config.tools_config

    # 使用工厂初始化内置工具
    tool_factory = ToolFactory(
        user_id_for_scope=user_id_for_scope,
        user_id=user_id,
        session_id=session_id,
        session_task_id=session_task_id,
        branch_name=branch_name,
        user_permission_role=user_permission_role,
        **kwargs,
    )

    processed_tools_set: set[str] = set()

    buildin_tool_init_res = ToolInitializationResult(
        tool_completion_params_map={},
        tool_closures_map={},
        enable_tools_set=set(),
        disable_tools_set=set(),
        explicit_tools_set=set(),
        implicit_tools_set=set(),
    )

    for tool_name, config in tools_config.items():
        if tool_name in processed_tools_set:
            raise ValueError(f"dublicate tool name: {tool_name}")
        tool_completion_param, tool_call_function = await tool_factory.prepare_tool(tool_name, config)
        buildin_tool_init_res.tool_completion_params_map[tool_name] = tool_completion_param
        buildin_tool_init_res.tool_closures_map[tool_name] = tool_call_function
        if config.enabled:
            buildin_tool_init_res.enable_tools_set.add(tool_name)
        else:
            buildin_tool_init_res.disable_tools_set.add(tool_name)
        if config.explicit:
            buildin_tool_init_res.explicit_tools_set.add(tool_name)
        else:
            buildin_tool_init_res.implicit_tools_set.add(tool_name)
        processed_tools_set.add(tool_name)

    # 准备 MCP 上下文管理器
    mcp_config = None
    if session_config.mcp_config and len(session_config.mcp_config.servers) > 0:
        mcp_config = session_config.mcp_config

    mcp_context: _EmptyAsyncContextManager | McpToolsLoader = _EmptyAsyncContextManager()
    if mcp_config and len(mcp_config.servers) > 0:
        mcp_context = await load_mcp_tools(mcp_config)  # type: ignore
    

    return buildin_tool_init_res, mcp_context