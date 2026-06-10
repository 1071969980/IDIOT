"""
copy_item 工具的实现
"""
from typing import Any
from uuid import UUID
from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure, ToolTaskResult
from api.juiceFS.client_worker.exceptions import (
    TaskExecutionError, TaskTimeoutError, WorkerPoolError
)
from .config_data_model import (
    CopyItemConfig,
    CopyItemParamDefine,
    COPY_ITEM_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend import JuiceFSSdkBackend


class CopyItemTool:
    """CopyItem 工具类"""

    def __init__(self, config: CopyItemConfig, storage_backend: FileOperationsStorageBackend):
        self.config = config
        self.storage_backend = storage_backend

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 1. 参数验证
        try:
            param = CopyItemParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join(
                f"{'.'.join(str(l) for l in err['loc'])} - {err['msg']}"
                for err in e.errors()
            )
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True
            )

        # 2. 业务逻辑验证
        if not param.source_path or not param.destination_path:
            return ToolTaskResult(
                str_content="错误: source_path 和 destination_path 不能为空",
                occur_error=True
            )

        # 3. 调用存储后端复制
        try:
            result = await self.storage_backend.copy_item(
                param.source_path,
                param.destination_path
            )
        except TaskExecutionError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except TaskTimeoutError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except WorkerPoolError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except FileNotFoundError:
            return ToolTaskResult(
                str_content=f"源路径不存在：{param.source_path}",
                occur_error=True
            )
        except FileExistsError:
            return ToolTaskResult(
                str_content=f"目标路径已存在：{param.destination_path}",
                occur_error=True
            )
        except ValueError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)

        if not result.success:
            return ToolTaskResult(
                str_content=result.message or "复制失败",
                occur_error=True
            )

        item_type_name = "目录" if result.item_type == "directory" else "文件"
        return ToolTaskResult(
            str_content=f"成功复制{item_type_name}: {param.source_path} -> {param.destination_path}",
            json_content={
                "action": "copy",
                "item_type": result.item_type,
                "source_path": param.source_path,
                "destination_path": param.destination_path,
                "success": True
            },
            occur_error=False
        )


def construct_copy_item(
    config: CopyItemConfig,
    scope_def: dict[str, Any],
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 CopyItemTool 实例"""

    session_id: UUID | None = kwargs.get("session_id")
    if session_id is None:
        raise ValueError("session_id is required")

    if config.storage_backend == "juicefs_sdk":
        from ..config_scope_data_model import resolve_file_ops_scope
        scope = resolve_file_ops_scope(config, scope_def)
        config = config.model_copy(update={"tool_scope": scope})
        storage_backend = JuiceFSSdkBackend(
            session_id=session_id,
            scope=scope,
        )
    elif config.storage_backend == "kwargs_DI":
        storage_backend: FileOperationsStorageBackend | None = kwargs.get("storage_backend")
        if storage_backend is None:
            raise ValueError("storage_backend must be provided in kwargs")
        if not isinstance(storage_backend, FileOperationsStorageBackend):
            raise TypeError("storage_backend must be an instance of FileOperationsStorageBackend")
    else:
        raise ValueError(f"Unknown storage_backend type: {config.storage_backend}")

    tool = CopyItemTool(config=config, storage_backend=storage_backend)

    return (COPY_ITEM_GENERATION_TOOL_PARAM, tool)


CONSTRUCTOR = {TOOL_NAME: construct_copy_item}