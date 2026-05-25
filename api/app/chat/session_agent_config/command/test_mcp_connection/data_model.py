from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TestMcpConnectionInput(BaseModel):
    mode: Literal["all", "single"] = Field(
        default="all",
        description="测试模式: 'all' 测试所有服务器, 'single' 测试单个服务器"
    )
    server_name: str | None = Field(
        default=None,
        description="要测试的服务器名称，仅在 mode='single' 时有效"
    )
    branch_name: str | None = Field(
        default=None,
        description="分支名称，用于读取有效配置"
    )


class McpToolInfo(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None


class ServerInfo(BaseModel):
    name: str | None = None
    protocol_version: str | None = None


class McpServerTestResult(BaseModel):
    server_name: str
    server_url: str
    status: Literal["success", "failed"]
    server_info: ServerInfo | None = None
    tools: list[McpToolInfo] = []
    tool_count: int = 0
    error_message: str | None = None
    error_type: str | None = None
    response_time_ms: float = 0.0
    tested_at: datetime


class TestMcpConnectionOutput(BaseModel):
    results: list[McpServerTestResult]
    total_servers: int = 0
    success_count: int = 0
    failed_count: int = 0
