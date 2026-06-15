from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any

from .data_model import ToolTaskResult

ToolClosure = Callable[..., Coroutine[Any, Any, ToolTaskResult]]


class UserToolCallingPermissionRole(str, Enum):
    OWNER = "owner"
    VISITOR = "visitor"