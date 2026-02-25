from pydantic import BaseModel
from typing import List, Optional
from ..get_tools_enabled_status.data_model import ToolEnabledStatus


class UpdateToolsEnabledStatusInput(BaseModel):
    session_id: str
    tools_status: List[ToolEnabledStatus]


class UpdateToolsEnabledStatusOutput(BaseModel):
    updated_tools: List[ToolEnabledStatus]
    success: bool
    message: Optional[str] = None
