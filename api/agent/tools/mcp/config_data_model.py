"""
MCP Client 配置数据模型
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator

# 导入项目的基础配置类
from api.agent.tools.config_data_model import SessionToolConfigBase


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


class McpServerConfig(BaseModel):
    """
    单个 MCP Server 配置

    Attributes:
        url: MCP Server 的 streamable HTTP URL
        name: Server 名称，用于日志和工具名称前缀
        timeout: 连接和调用超时时间（秒）
        tool_filter: 工具过滤配置
    """
    url: str = Field(
        description="MCP Server 的 streamable HTTP URL (例如: http://localhost:8000/mcp)"
    )
    name: str = Field(
        description="Server 名称，用于日志和错误信息"
    )
    timeout: float = Field(
        default=30.0,
        description="连接和调用超时时间（秒）"
    )
    json_response: bool = Field(
        default=False,
        description=(
            "MCP 响应模式。"
            "False 使用 SSE 模式（支持日志和进度通知）；"
            "True 使用 JSON 模式（仅返回最终结果）。"
        )
    )
    include_server_name_in_tool_name: bool = Field(
        default=True,
        description=(
            "是否在工具名称前添加 server 前缀。"
            "如果连接多个 server，建议设置为 True 以避免工具名冲突。"
        )
    )
    tool_filter: McpToolFilter = Field(
        default_factory=McpToolFilter,
        description="工具过滤配置"
    )


class McpClientConfig(BaseModel):
    """
    MCP Client 工具配置

    支持连接多个 MCP Server，并过滤可用工具。

    Attributes:
        enabled: 是否启用 MCP Client
        servers: 要连接的 MCP Server 列表
    """
    enabled: bool = True

    servers: list[McpServerConfig] = Field(
        default_factory=list,
        description="要连接的 MCP Server 列表"
    )