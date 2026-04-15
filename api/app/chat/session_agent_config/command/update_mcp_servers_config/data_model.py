from pydantic import BaseModel, Field

from api.agent.tools.mcp.config_data_model import McpServerConfig


class UpdateMcpServersConfigInput(BaseModel):
    servers: list[McpServerConfig] = Field(description="MCP 服务器配置列表")
    branch_name: str = Field(description="分支名称")


class UpdateMcpServersConfigOutput(BaseModel):
    servers: list[McpServerConfig]
