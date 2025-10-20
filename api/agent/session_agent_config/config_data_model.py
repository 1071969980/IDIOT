from typing import Any

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from api.agent.tools.config_data_model import SessionToolConfigBase

CURRENT_VERSION = "v0.1"

DEFAULT_TOOLS_CONFIG = {
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
                    pass
            else:
                raise ValidationError("version is required")
        else:
            raise ValidationError("data must be dict")
