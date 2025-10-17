from collections.abc import Callable, Coroutine
from typing import Any
from .data_model import ToolTaskResult

ToolClosure = Callable[..., Coroutine[Any, Any, ToolTaskResult]]