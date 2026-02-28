"""
MCP 连接测试命令数据模型
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TestModeEnum(str, Enum):
    """测试模式枚举"""
    SINGLE = "single"  # 测试单个 Server
    ALL = "all"  # 测试所有 Server


class ConnectionStatusEnum(str, Enum):
    """连接状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"


class ToolInfo(BaseModel):
    """工具信息"""
    name: str = Field(description="工具名称")
    description: Optional[str] = Field(default=None, description="工具描述")
    input_schema: Optional[dict[str, Any]] = Field(default=None, description="工具输入参数 Schema")


class ServerInfo(BaseModel):
    """服务器信息"""
    name: str = Field(description="服务器名称")
    protocol_version: Optional[str] = Field(default=None, description="MCP 协议版本")


class McpServerTestResult(BaseModel):
    """单个 MCP Server 测试结果"""
    server_name: str = Field(description="服务器名称")
    server_url: str = Field(description="服务器 URL")
    status: ConnectionStatusEnum = Field(description="连接状态")

    # 连接成功时的详细信息
    server_info: Optional[ServerInfo] = Field(default=None, description="服务器信息")
    tools: list[ToolInfo] = Field(default_factory=list, description="可用工具列表")
    tool_count: int = Field(default=0, description="工具数量")

    # 连接失败时的错误信息
    error_message: Optional[str] = Field(default=None, description="错误信息")
    error_type: Optional[str] = Field(default=None, description="错误类型（异常类名）")

    # 测试元数据
    response_time_ms: Optional[float] = Field(default=None, description="响应时间（毫秒）")
    tested_at: datetime = Field(default_factory=datetime.now, description="测试时间")


class TestMcpConnectionInput(BaseModel):
    """测试 MCP 连接的输入参数"""
    session_id: str = Field(description="会话 ID，用于获取已保存的 MCP 配置")
    mode: TestModeEnum = Field(
        default=TestModeEnum.ALL,
        description="测试模式：single=测试单个服务器，all=测试所有服务器"
    )
    server_name: Optional[str] = Field(
        default=None,
        description="要测试的服务器名称，仅在 mode=single 时有效"
    )


class TestMcpConnectionOutput(BaseModel):
    """测试 MCP 连接的输出结果"""
    session_id: str = Field(description="会话 ID")
    results: list[McpServerTestResult] = Field(
        default_factory=list,
        description="各服务器的测试结果列表"
    )

    # 汇总信息
    total_servers: int = Field(default=0, description="测试的服务器总数")
    success_count: int = Field(default=0, description="连接成功的服务器数")
    failed_count: int = Field(default=0, description="连接失败的服务器数")

    # 整体状态
    success: bool = Field(default=True, description="整体操作是否成功")
    message: Optional[str] = Field(default=None, description="操作消息")