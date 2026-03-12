from pydantic import BaseModel
from typing import List, Optional

from api.agent.tools.mcp.config_data_model import McpServerConfig


class UpdateMcpServersConfigInput(BaseModel):
    servers: List[McpServerConfig]


class UpdateMcpServersConfigOutput(BaseModel):
    servers: List[McpServerConfig]
    success: bool
    message: Optional[str] = None
