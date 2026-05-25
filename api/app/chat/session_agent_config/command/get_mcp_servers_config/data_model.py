from pydantic import BaseModel, Field

from api.agent.tools.mcp.config_data_model import McpServerConfig


class GetMcpServersConfigInput(BaseModel):
    branch_name: str | None = Field(
        default=None,
        description="分支名称。为空则只读取基础配置"
    )


class GetMcpServersConfigOutput(BaseModel):
    servers: list[McpServerConfig]
