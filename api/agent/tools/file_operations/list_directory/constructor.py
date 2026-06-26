"""
list_directory 工具的实现
提供目录列表功能，能够清楚区分文件和目录
"""

import asyncio
from typing import Any, cast
import os

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

# 导入项目的基础类型
from api.agent.tools.type import ToolClosure, ToolTaskResult
from api.juiceFS.client_worker.exceptions import (
    TaskExecutionError, TaskTimeoutError, WorkerPoolError, TaskCancelledError,
)
from .config_data_model import (
    ListDirectoryConfig,
    ListDirectoryParamDefine,
    LIST_DIRECTORY_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
# 导入存储后端
from ..storage_backend.base import FileOperationsStorageBackend, DirectoryItem
from ..storage_backend import JuiceFSSdkBackend
# 导入目录列表工具函数
from .utils import format_directory_tree


class ListDirectoryTool(object):
    """
    ListDirectory 工具类

    提供列出目录内容的功能，能够清楚地区分文件和目录。
    """

    def __init__(self, config: ListDirectoryConfig, storage_backend: FileOperationsStorageBackend):
        """
        初始化工具

        Args:
            config: 工具配置
            storage_backend: 存储后端实例（已持有 session_id）
        """
        self.config = config
        self.storage_backend = storage_backend

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        工具的调用入口

        Args:
            **kwargs: LLM 传递的参数

        Returns:
            ToolTaskResult: 执行结果
        """
        # 提取 cancel_event（由 base_agent 注入），传递给存储后端
        cancel_event = cast(asyncio.Event | None, kwargs.get("cancel_event"))
        if cancel_event and cancel_event.is_set():
            return ToolTaskResult(
                str_content="目录列表已被用户取消",
                occur_error=True,
            )

        # 1. 参数验证
        try:
            param = ListDirectoryParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join(
                f"{'.'.join(str(l) for l in err['loc'])} - {err['msg']}"
                for err in e.errors()
            )
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True
            )

        # 2. 设置默认路径（如果未提供）
        directory_path = param.directory_path or "."

        # 3. 调用存储后端列出目录
        try:
            directory_items = await self.storage_backend.list_directory(
                directory_path, cancel_event=cancel_event,
            )
        except TaskCancelledError:
            return ToolTaskResult(
                str_content="目录列表已被用户取消",
                occur_error=True,
            )
        except TaskExecutionError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except TaskTimeoutError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except WorkerPoolError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except ValueError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)

        # Format the output using the utility function
        formatted_content = format_directory_tree(directory_items, directory_path)

        return ToolTaskResult(
            str_content=formatted_content,
            occur_error=False
        )


def construct_list_directory(
    config: ListDirectoryConfig,
    scope_def: dict[str, Any],
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 ListDirectoryTool 实例

    Args:
        config: 工具配置
        scope_def: 作用域定义字典
        **kwargs: 依赖参数
            - session_id (UUID, 必需): 用于注入到存储后端
            - storage_backend (FileOperationsStorageBackend, 可选): 当 config.storage_backend="kwargs_DI" 时必需

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """

    # 1. 提取 session_id（必需）
    from uuid import UUID
    session_id: UUID | None = kwargs.get("session_id")  # type: ignore
    if session_id is None:
        raise ValueError("session_id is required")

    # 2. 根据 config.storage_backend 创建存储后端
    if config.storage_backend == "juicefs_sdk":
        from ..config_scope_data_model import resolve_file_ops_scope
        scope = config.tool_scope or resolve_file_ops_scope(scope_def)
        config = config.model_copy(update={"tool_scope": scope})
        storage_backend = JuiceFSSdkBackend(
            session_id=session_id,
            scope=scope,
        )

    elif config.storage_backend == "kwargs_DI":
        # 模式 4: 依赖注入
        storage_backend: FileOperationsStorageBackend | None = kwargs.get("storage_backend")  # type: ignore

        if storage_backend is None:
            raise ValueError(
                "storage_backend must be provided in kwargs "
                "when config.storage_backend='kwargs_DI'"
            )

        # 类型验证
        if not isinstance(storage_backend, FileOperationsStorageBackend):
            raise TypeError(
                f"storage_backend must be an instance of FileOperationsStorageBackend, "
                f"got {type(storage_backend).__name__}"
            )

    else:
        # 不应该到达这里（Pydantic 会验证 config.storage_backend）
        raise ValueError(f"Unknown storage_backend type: {config.storage_backend}")

    # 4. 创建工具实例
    tool = ListDirectoryTool(config=config, storage_backend=storage_backend)

    # 5. 返回工具定义和闭包
    return (
        LIST_DIRECTORY_GENERATION_TOOL_PARAM,
        tool
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_list_directory}