from pydantic import BaseModel
from typing import List, Optional

from api.agent.tools.mcp.config_data_model import McpServerConfig


class GetMcpServersConfigInput(BaseModel):
    pass


class GetMcpServersConfigOutput(BaseModel):
    servers: List[McpServerConfig]
    success: bool = True
    message: Optional[str] = None
