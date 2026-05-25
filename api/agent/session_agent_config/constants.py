from __future__ import annotations

from typing import Annotated, Union, Literal, Any, Sequence
from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from api.agent.tools.ask_user.config_data_model import DEFAULT_TOOL_CONFIG as ASK_USER_DEFAULT_CONFIG
from api.agent.tools.todo.config_data_model import DEFAULT_TOOL_CONFIG as TODO_WRITE_DEFAULT_CONFIG
from api.agent.tools.file_operations.read_file.config_data_model import DEFAULT_TOOL_CONFIG as READ_FILE_DEFAULT_CONFIG
from api.agent.tools.file_operations.edit_file.config_data_model import DEFAULT_TOOL_CONFIG as EDIT_FILE_DEFAULT_CONFIG
from api.agent.tools.file_operations.write_file.config_data_model import DEFAULT_TOOL_CONFIG as WRITE_FILE_DEFAULT_CONFIG
from api.agent.tools.file_operations.list_directory.config_data_model import DEFAULT_TOOL_CONFIG as LIST_DIRECTORY_DEFAULT_CONFIG
from api.agent.tools.file_operations.move_file.config_data_model import DEFAULT_TOOL_CONFIG as MOVE_ITEM_DEFAULT_CONFIG
from api.agent.tools.file_operations.copy_file.config_data_model import DEFAULT_TOOL_CONFIG as COPY_ITEM_DEFAULT_CONFIG
from api.agent.tools.file_operations.delete_file.config_data_model import DEFAULT_TOOL_CONFIG as DELETE_ITEM_DEFAULT_CONFIG
from api.agent.tools.bash.config_data_model import DEFAULT_TOOL_CONFIG as BASH_DEFAULT_CONFIG
from api.agent.tools.skills.load_skill.config_data_model import DEFAULT_TOOL_CONFIG as LOAD_SKILL_DEFAULT_CONFIG
from api.agent.tools.skills.unload_skill.config_data_model import DEFAULT_TOOL_CONFIG as UNLOAD_SKILL_DEFAULT_CONFIG

from api.agent.tools.sub_agent.config_data_model import DEFAULT_TOOL_CONFIG as SUB_AGENT_DEFAULT_CONFIG

from api.agent.tools.mcp.config_data_model import McpClientConfig

from .config_data_model import (SessionAgentConfigVersion,
                                ToolConfigUnion,
                                SessionSystemPromptConfig,
                                SessionSystemPromptDefByPlainText,
                                SessionSystemPromptDefByVariable,
                                SessionSystemPromptDefByLangFuse,
                                SessionSystemPromptDefByJinja,
                                SessionSystemPromptDefByJinjaString,
                                SessionSystemPromptDefUnion,
                                SessionAgentConfig)

# ---
# Magic strings
# ---

SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT = "session_config_overlay"

# ---
# Sub agent tool filter
# ---

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
    **UNLOAD_SKILL_DEFAULT_CONFIG,

    **SUB_AGENT_DEFAULT_CONFIG,
}

# ---
# Default tool configs
# ---


DEFAULT_MAIN_AGENT_TOOLS_CONFIG : dict[str, ToolConfigUnion] = {
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
    **UNLOAD_SKILL_DEFAULT_CONFIG,

    **SUB_AGENT_DEFAULT_CONFIG,
}

# ---
# Default system configs
# ---


DEFAULT_MAIN_AGENT_SYSTEM_PROMPT_CONFIG = [
    SessionSystemPromptDefByLangFuse(
        index=0,
        prompt_path=PurePosixPath("main_agent/system_prompt"),
        production=True,
    ),
]

# ---
# Default agent config
# ---


DEFAULT_MAIN_AGENT_SESSION_CONFIG = SessionAgentConfig(
    version=SessionAgentConfigVersion(major=0, minor=1, patch=0),
    system_prompt_config=SessionSystemPromptConfig(
        prompt_defs=DEFAULT_MAIN_AGENT_SYSTEM_PROMPT_CONFIG,
    ),
    tools_config=DEFAULT_MAIN_AGENT_TOOLS_CONFIG,
    mcp_config=None,
    allowed_rel_dirs_in_juicefs_for_tool=[PurePosixPath("./")],
)