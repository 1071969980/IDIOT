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
            tool_closures[tool_param["function"]["name"]] = wrapper

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
