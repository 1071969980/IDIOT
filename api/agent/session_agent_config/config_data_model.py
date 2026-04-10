from enum import Enum
from typing import Union, Literal, Any
from pathlib import PurePosixPath

from pydantic import BaseModel

from api.agent.tools.ask_user.config_data_model import DEFAULT_TOOL_CONFIG as ASK_USER_DEFAULT_CONFIG, AskUserChoiceConfig
from api.agent.tools.todo.config_data_model import DEFAULT_TOOL_CONFIG as TODO_WRITE_DEFAULT_CONFIG, TodoWriteConfig
from api.agent.tools.file_operations.read_file.config_data_model import DEFAULT_TOOL_CONFIG as READ_FILE_DEFAULT_CONFIG, ReadFileConfig
from api.agent.tools.file_operations.edit_file.config_data_model import DEFAULT_TOOL_CONFIG as EDIT_FILE_DEFAULT_CONFIG, EditFileConfig
from api.agent.tools.file_operations.write_file.config_data_model import DEFAULT_TOOL_CONFIG as WRITE_FILE_DEFAULT_CONFIG, WriteFileConfig
from api.agent.tools.file_operations.list_directory.config_data_model import DEFAULT_TOOL_CONFIG as LIST_DIRECTORY_DEFAULT_CONFIG, ListDirectoryConfig
from api.agent.tools.file_operations.move_file.config_data_model import DEFAULT_TOOL_CONFIG as MOVE_ITEM_DEFAULT_CONFIG, MoveItemConfig
from api.agent.tools.file_operations.copy_file.config_data_model import DEFAULT_TOOL_CONFIG as COPY_ITEM_DEFAULT_CONFIG, CopyItemConfig
from api.agent.tools.file_operations.delete_file.config_data_model import DEFAULT_TOOL_CONFIG as DELETE_ITEM_DEFAULT_CONFIG, DeleteItemConfig
from api.agent.tools.bash.config_data_model import DEFAULT_TOOL_CONFIG as BASH_DEFAULT_CONFIG, BashConfig
from api.agent.tools.skills.load_skill.config_data_model import DEFAULT_TOOL_CONFIG as LOAD_SKILL_DEFAULT_CONFIG, LoadSkillConfig
from api.agent.tools.skills.skill_advisor.config_data_model import DEFAULT_TOOL_CONFIG as SKILL_ADVISOR_DEFAULT_CONFIG, SkillAdvisorConfig
from api.agent.tools.sub_agent.config_data_model import DEFAULT_TOOL_CONFIG as SUB_AGENT_DEFAULT_CONFIG, SubAgentToolConfig

from api.agent.tools.mcp.config_data_model import McpClientConfig

SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT = "session_config_overlay"

# 工具配置的 Union 类型，用于 Pydantic 正确序列化子类字段
# 添加新工具时需要在此处添加对应的配置类

ToolConfigUnion = Union[
    AskUserChoiceConfig,
    TodoWriteConfig,
    ReadFileConfig,
    EditFileConfig,
    WriteFileConfig,
    ListDirectoryConfig,
    MoveItemConfig,
    CopyItemConfig,
    DeleteItemConfig,
    BashConfig,
    LoadSkillConfig,
    SkillAdvisorConfig,
    SubAgentToolConfig,
]

DEFAULT_TOOLS_CONFIG : dict[str, ToolConfigUnion] = {
    **ASK_USER_DEFAULT_CONFIG,
    **TODO_WRITE_DEFAULT_CONFIG,
    **READ_FILE_DEFAULT_CONFIG,
    **EDIT_FILE_DEFAULT_CONFIG,
    **WRITE_FILE_DEFAULT_CONFIG,
    **LIST_DIRECTORY_DEFAULT_CONFIG,
    **MOVE_ITEM_DEFAULT_CONFIG,
    **COPY_ITEM_DEFAULT_CONFIG,
    **DELETE_ITEM_DEFAULT_CONFIG,
    **BASH_DEFAULT_CONFIG,
    **LOAD_SKILL_DEFAULT_CONFIG,
    **SKILL_ADVISOR_DEFAULT_CONFIG,
    **SUB_AGENT_DEFAULT_CONFIG,
}

AVILABLE_TOOLS_CONFIG_FOR_SUB_AGENT: dict[str, ToolConfigUnion] = {
    **TODO_WRITE_DEFAULT_CONFIG,
    **READ_FILE_DEFAULT_CONFIG,
    **EDIT_FILE_DEFAULT_CONFIG,
    **WRITE_FILE_DEFAULT_CONFIG,
    **LIST_DIRECTORY_DEFAULT_CONFIG,
    **MOVE_ITEM_DEFAULT_CONFIG,
    **COPY_ITEM_DEFAULT_CONFIG,
    **DELETE_ITEM_DEFAULT_CONFIG,
    **BASH_DEFAULT_CONFIG,
    **LOAD_SKILL_DEFAULT_CONFIG,
    **SKILL_ADVISOR_DEFAULT_CONFIG,
    **SUB_AGENT_DEFAULT_CONFIG,
}

class SessionSystemPromptDef(BaseModel):
    index: int

class SessionSystemPromptDefByPlainText(SessionSystemPromptDef):
    type: Literal["plain_text"] = "plain_text"
    text: str = ""

class SessionSystemPromptDefByLangFuse(SessionSystemPromptDef):
    type: Literal["langfuse"] = "langfuse"
    prompt_path: PurePosixPath
    production: bool = True
    label: str | None = None
    version: int | None  = None
    params: dict[str, SessionSystemPromptDef] | None = None

class SessionSystemPromptDefByJinja(SessionSystemPromptDef):
    type: Literal["jinja"] = "jinja"
    template_rel_path: PurePosixPath
    params: dict[str, SessionSystemPromptDef | Any] | None = None

class SessionSystemPromptDefByJinjaString(SessionSystemPromptDef):
    type: Literal["jinja_string"] = "jinja_string"
    template: str
    params: dict[str, SessionSystemPromptDef | Any] | None = None

class SessionSystemPromptConfig(BaseModel):
    prompt_defs: list[SessionSystemPromptDef] = []
    white_list: list[int] | None = None
    black_list: list[int] | None = None

class SessionAgentConfig(BaseModel):
    system_prompt_config: SessionSystemPromptConfig = SessionSystemPromptConfig()
    tools_config: dict[str, ToolConfigUnion] = DEFAULT_TOOLS_CONFIG
    mcp_config: McpClientConfig | None = None