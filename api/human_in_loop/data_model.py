"""Neutral HIL domain models.

This module deliberately has no Redis/runtime dependencies so that both the
HIL transport code and the session event model layer can import these models
without creating circular imports.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


class _HilContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HILInterruptContentAgentToolCallBodyType(str, Enum):
    ChoiceForm = "ChoiceForm"


class HILInterruptContentAgentToolCallBody(_HilContentModel):
    tool_name: str
    type: HILInterruptContentAgentToolCallBodyType
    tool_exec_uuid: str
    detail: Any

    @field_validator("detail")
    @classmethod
    def validate_detail_json_serializable(cls, v: Any) -> Any:
        """Validate that ``detail`` can be represented as JSON."""
        if isinstance(v, BaseModel):
            try:
                return v.model_dump(mode="json")
            except Exception as e:
                raise ValueError(
                    f"detail字段中的Pydantic模型无法序列化为JSON: {e}"
                ) from e

        try:
            json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"detail字段无法序列化为JSON: {e}") from e
        return v


class HILInterruptContent(_HilContentModel):
    source: Literal["agent_tool_call"]
    body: HILInterruptContentAgentToolCallBody


class HILNotificationContentAgentToolCallBodyType(str, Enum):
    Info = "Info"


class HILNotificationContentAgentToolCallBody(_HilContentModel):
    tool_name: str
    type: HILNotificationContentAgentToolCallBodyType
    tool_exec_uuid: str
    detail: Any

    @field_validator("detail")
    @classmethod
    def validate_detail_json_serializable(cls, v: Any) -> Any:
        """Validate that ``detail`` can be represented as JSON."""
        if isinstance(v, BaseModel):
            try:
                return v.model_dump(mode="json")
            except Exception as e:
                raise ValueError(
                    f"detail字段中的Pydantic模型无法序列化为JSON: {e}"
                ) from e

        try:
            json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"detail字段无法序列化为JSON: {e}") from e
        return v


class HILNotificationContent(_HilContentModel):
    source: Literal["agent_tool_call"]
    body: HILNotificationContentAgentToolCallBody
