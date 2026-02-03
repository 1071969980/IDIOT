from typing import Any

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from api.agent.tools.config_data_model import SessionToolConfigBase
from api.agent.tools.a2a_chat_task.config_data_model import DEFAULT_TOOL_CONFIG as A2A_CHAT_TASK_DEFAULT_CONFIG
from api.agent.tools.ask_user.config_data_model import DEFAULT_TOOL_CONFIG as ASK_USER_DEFAULT_CONFIG
from api.agent.tools.todo.config_data_model import DEFAULT_TOOL_CONFIG as TODO_WRITE_DEFAULT_CONFIG
from api.agent.tools.file_operations.read_file.config_data_model import DEFAULT_TOOL_CONFIG as READ_FILE_DEFAULT_CONFIG
from api.agent.tools.file_operations.edit_file.config_data_model import DEFAULT_TOOL_CONFIG as EDIT_FILE_DEFAULT_CONFIG
from api.agent.tools.file_operations.write_file.config_data_model import DEFAULT_TOOL_CONFIG as WRITE_FILE_DEFAULT_CONFIG

from api.agent.tools.mcp.config_data_model import McpClientConfig

CURRENT_VERSION = "v0.1"

DEFAULT_TOOLS_CONFIG : dict[str, SessionToolConfigBase] = {
    # **A2A_CHAT_TASK_DEFAULT_CONFIG,
    **ASK_USER_DEFAULT_CONFIG,
    **TODO_WRITE_DEFAULT_CONFIG,
    **READ_FILE_DEFAULT_CONFIG,
    **EDIT_FILE_DEFAULT_CONFIG,
    **WRITE_FILE_DEFAULT_CONFIG,
}

AVILABLE_TOOLS_CONFIG_FOR_SUB_AGENT: dict[str, SessionToolConfigBase] = {
    **TODO_WRITE_DEFAULT_CONFIG,
    **READ_FILE_DEFAULT_CONFIG,
    **EDIT_FILE_DEFAULT_CONFIG,
    **WRITE_FILE_DEFAULT_CONFIG,
}

class SessionAgentConfig(BaseModel):
    version: str
    tools_config: dict[str, SessionToolConfigBase] = DEFAULT_TOOLS_CONFIG
    mcp_config: McpClientConfig | None = None

    # 验证版本号必须已v开头
    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.startswith("v"):
            # raise ValidationError("version must start with 'v'")
            raise ValidationError.from_exception_data(
                "version must start with 'v'",
                [
                    {
                        'type': 'value_error',
                        'loc': ('version',),
                        'input': v,
                    }
                ]
            )
        return v
    
    @model_validator(mode="before")
    @classmethod
    def migration(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "version" in data:
                if data["version"] == CURRENT_VERSION:
                    return data
                else:
                    # TODO: 添加版本升级逻辑
                    # raise ValidationError("version is not supported")
                    raise ValidationError.from_exception_data(
                        "version is not supported",
                        [
                            {
                                'type': 'value_error',
                                'loc': ('version',),
                                'input': data["version"],
                            }
                        ]
                    )
            else:
                # raise ValidationError("version is required")
                raise ValidationError.from_exception_data(
                    "version is required",
                    [
                        {
                            'type': 'value_error',
                            'loc': ('version',),
                            'input': None,
                        }
                    ]
                )
        else:
            # raise ValidationError("data must be dict")
            raise ValueError("data must be dict")
