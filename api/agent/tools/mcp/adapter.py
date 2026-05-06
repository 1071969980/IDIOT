"""
MCP Client 主适配器

提供对外 API，将 MCP 工具转换为 Agent 可用的工具列表。
"""
from typing import TYPE_CHECKING

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure
from .config_data_model import McpClientConfig, McpToolFilter
from .client import McpClientManager
from .tool_mapper import McpToolWrapper

from api.chat.data_model import ToolInitializationResult


class McpToolsLoader:
    """
    MCP 工具加载器

    使用上下文管理器确保连接正确关闭。
    """

    def __init__(self, config: McpClientConfig):
        self.config = config
        self.manager: McpClientManager | None = None
        self.tool_completion_params_map: dict[str, ChatCompletionToolParam] = {}
        self.tool_closures_map: dict[str, ToolClosure] = {}
        self.enable_tools_set: set[str] = set()
        self.disable_tools_set: set[str] = set()
        self.explicit_tools_set: set[str] = set()
        self.implicit_tools_set: set[str] = set()

    
    def should_enable_tool(self, tool_name: str, filter_config: McpToolFilter) -> bool:
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

    async def __aenter__(self):
        """建立连接并加载工具"""
        self.manager = McpClientManager(self.config)
        # 让 manager 对每一个 server 建立连接。
        await self.manager.__aenter__()

        # 获取每一个 server 的工具
        all_tools = await self.manager.get_all_tools()

        processed_tools_set: set[str] = set()

        for server_name, tool_and_connection_list in all_tools.items():
            for mcp_tool, connection in tool_and_connection_list:
                # 创建工具包装器
                prefix = f"{server_name}__" \
                    if connection.include_server_name_in_tool_name else ""

                wrapper = McpToolWrapper(
                    mcp_tool=mcp_tool,
                    connection=connection,
                    tool_name_prefix=prefix
                )

                # 添加工具到属性
                tool_full_name = wrapper.get_full_name()
                if tool_full_name in processed_tools_set:
                    raise ValueError(f"dublicate tool name: {tool_full_name}, when load tools from {server_name}")

                tool_param = wrapper.get_tool_param()
                self.tool_completion_params_map[tool_full_name] = tool_param
                self.tool_closures_map[tool_full_name] = wrapper
                if self.should_enable_tool(tool_full_name, connection.tool_filter):
                    self.enable_tools_set.add(tool_full_name)
                else:
                    self.disable_tools_set.add(tool_full_name)
                if connection.explicit:
                    self.explicit_tools_set.add(tool_full_name)
                else:
                    self.implicit_tools_set.add(tool_full_name)
                
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭连接"""
        if self.manager:
            await self.manager.__aexit__(exc_type, exc_val, exc_tb)
    def get_tools(self) -> ToolInitializationResult:
        """
        获取工具列表
        """
        return ToolInitializationResult(
            tool_completion_params_map=self.tool_completion_params_map,
            tool_closures_map=self.tool_closures_map,
            enable_tools_set=self.enable_tools_set,
            disable_tools_set=self.disable_tools_set,
            explicit_tools_set=self.explicit_tools_set,
            implicit_tools_set=self.implicit_tools_set,
            allowed_rel_dirs_in_juicefs_for_tool=set(),
        )


async def load_mcp_tools(config: McpClientConfig) -> McpToolsLoader:
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
