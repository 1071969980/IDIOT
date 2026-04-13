from __future__ import annotations

from typing import Annotated, Union, Literal, Any, Sequence
from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from api.agent.tools.ask_user.config_data_model import AskUserChoiceConfig
from api.agent.tools.todo.config_data_model import TodoWriteConfig
from api.agent.tools.file_operations.read_file.config_data_model import ReadFileConfig
from api.agent.tools.file_operations.edit_file.config_data_model import EditFileConfig
from api.agent.tools.file_operations.write_file.config_data_model import WriteFileConfig
from api.agent.tools.file_operations.list_directory.config_data_model import ListDirectoryConfig
from api.agent.tools.file_operations.move_file.config_data_model import MoveItemConfig
from api.agent.tools.file_operations.copy_file.config_data_model import CopyItemConfig
from api.agent.tools.file_operations.delete_file.config_data_model import DeleteItemConfig
from api.agent.tools.bash.config_data_model import BashConfig
from api.agent.tools.skills.load_skill.config_data_model import LoadSkillConfig
from api.agent.tools.skills.skill_advisor.config_data_model import SkillAdvisorConfig
from api.agent.tools.sub_agent.config_data_model import SubAgentToolConfig

from api.agent.tools.mcp.config_data_model import McpClientConfig

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

class SessionSystemPromptDef(BaseModel):
    index: int

class SessionSystemPromptDefByPlainText(SessionSystemPromptDef):
    type: Literal["plain_text"] = "plain_text"
    text: str = ""

class SessionSystemPromptDefByVariable(SessionSystemPromptDef):
    type: Literal["variable"] = "variable"
    variable_name: str

class SessionSystemPromptDefByLangFuse(SessionSystemPromptDef):
    type: Literal["langfuse"] = "langfuse"
    prompt_path: PurePosixPath
    production: bool = True
    label: str | None = None
    version: int | None  = None
    params: dict[str, SessionSystemPromptDefUnion] | None = None

class SessionSystemPromptDefByJinja(SessionSystemPromptDef):
    type: Literal["jinja"] = "jinja"
    template_rel_path: PurePosixPath
    params: dict[str, SessionSystemPromptDefUnion | Any] | None = None

class SessionSystemPromptDefByJinjaString(SessionSystemPromptDef):
    type: Literal["jinja_string"] = "jinja_string"
    template: str
    params: dict[str, SessionSystemPromptDefUnion | Any] | None = None

SessionSystemPromptDefUnion = Annotated[
    Union[
        SessionSystemPromptDefByPlainText,
        SessionSystemPromptDefByVariable,
        SessionSystemPromptDefByLangFuse,
        SessionSystemPromptDefByJinja,
        SessionSystemPromptDefByJinjaString,
    ],
    Field(discriminator="type"),
]

class SessionSystemPromptConfig(BaseModel):
    prompt_defs: Sequence[SessionSystemPromptDefUnion]
    white_list: Sequence[int] | None = None
    black_list: Sequence[int] | None = None

class SessionAgentConfig(BaseModel):
    system_prompt_config: SessionSystemPromptConfig
    tools_config: dict[str, ToolConfigUnion]
    mcp_config: McpClientConfig | None
    work_dirs: list[PurePosixPath]