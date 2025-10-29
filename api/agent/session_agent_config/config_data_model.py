from typing import Any

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from api.agent.tools.config_data_model import SessionToolConfigBase
from api.agent.tools.a2a_chat_task.config_data_model import DEFAULT_TOOL_CONFIG as A2A_CHAT_TASK_DEFAULT_CONFIG

CURRENT_VERSION = "v0.1"

DEFAULT_TOOLS_CONFIG = {
    **A2A_CHAT_TASK_DEFAULT_CONFIG,
}

class SessionAgentConfig(BaseModel):
    version: str
    tools_config: dict[str, SessionToolConfigBase] = DEFAULT_TOOLS_CONFIG

    # 验证版本号必须已v开头
    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.startswith("v"):
            raise ValidationError("version must start with 'v'")
    
    @model_validator(mode="before")
    @classmethod
    def migration(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "version" in data:
                if data["version"] == CURRENT_VERSION:
                    return data
                else:
                    # TODO: 添加版本升级逻辑
                    raise ValidationError("version is not supported")
            else:
                raise ValidationError("version is required")
        else:
            raise ValidationError("data must be dict")
