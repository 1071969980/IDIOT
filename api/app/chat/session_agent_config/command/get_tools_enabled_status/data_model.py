from pydantic import BaseModel, field_validator
from typing import List, Optional
from enum import Enum

# 从各工具模块导入 TOOL_NAME 常量
from api.agent.tools.a2a_chat_task.config_data_model import TOOL_NAME as COMMUNICATION_TASK
from api.agent.tools.file_operations.write_file.config_data_model import TOOL_NAME as WRITE_FILE
from api.agent.tools.file_operations.list_directory.config_data_model import TOOL_NAME as LIST_DIRECTORY
from api.agent.tools.file_operations.edit_file.config_data_model import TOOL_NAME as EDIT_FILE
from api.agent.tools.sub_agent.config_data_model import TOOL_NAME as SUB_AGENT
from api.agent.tools.file_operations.read_file.config_data_model import TOOL_NAME as READ_FILE
from api.agent.tools.todo.config_data_model import TOOL_NAME as TODO_WRITE
from api.agent.tools.agent_roles.list_available_agent_roles.config_data_model import TOOL_NAME as LIST_AVAILABLE_AGENT_ROLES
from api.agent.tools.agent_roles.update_role_converstion_strategies.config_data_model import TOOL_NAME as UPDATE_CONVERSATION_STRATEGIES_OF_ROLE
from api.agent.tools.ask_user.config_data_model import TOOL_NAME as ASK_USER_CHOICE


# 定义所有可用的工具名称枚举
class ToolNameEnum(str, Enum):
    ASK_USER_CHOICE = ASK_USER_CHOICE
    TODO_WRITE = TODO_WRITE
    READ_FILE = READ_FILE
    EDIT_FILE = EDIT_FILE
    WRITE_FILE = WRITE_FILE
    LIST_DIRECTORY = LIST_DIRECTORY


class ToolEnabledStatus(BaseModel):
    tool_name: ToolNameEnum
    enabled: bool


class GetToolsEnabledStatusInput(BaseModel):
    session_id: str
    tool_names: Optional[List[ToolNameEnum]] = None  # 为空表示获取所有工具

    @field_validator('tool_names', mode='before')
    @classmethod
    def validate_tool_names(cls, v):
        if v is None:
            return None
        # 确保是列表
        if not isinstance(v, list):
            raise ValueError('tool_names must be a list')
        return v


class GetToolsEnabledStatusOutput(BaseModel):
    tools_status: List[ToolEnabledStatus]
    success: bool = True
    message: Optional[str] = None
