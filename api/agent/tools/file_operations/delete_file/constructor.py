"""
delete_item 工具的实现
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
    DeleteItemConfig,
    DeleteItemParamDefine,
    DELETE_ITEM_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend import JuiceFSSdkBackend


class DeleteItemTool:
    """DeleteItem 工具类"""

    def __init__(self, config: DeleteItemConfig, storage_backend: FileOperationsStorageBackend):
        self.config = config
        self.storage_backend = storage_backend

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 1. 参数验证
        try:
            param = DeleteItemParamDefine.model_validate(kwargs)
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
        if not param.path:
            return ToolTaskResult(
                str_content="错误: path 不能为空",
                occur_error=True
            )

        # 3. 调用存储后端删除
        try:
            result = await self.storage_backend.delete_item(param.path)
        except TaskExecutionError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except TaskTimeoutError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except WorkerPoolError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except ValueError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)

        if not result.success:
            return ToolTaskResult(
                str_content=result.message or "删除失败",
                occur_error=True
            )

        item_type_name = "目录" if result.item_type == "directory" else "文件"
        return ToolTaskResult(
            str_content=f"成功删除{item_type_name}: {param.path}",
            json_content={
                "action": "delete",
                "item_type": result.item_type,
                "path": param.path,
                "success": True
            },
            occur_error=False
        )


def construct_delete_item(
    config: DeleteItemConfig,
    scope_def: dict[str, Any],
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 DeleteItemTool 实例"""

    session_id: UUID | None = kwargs.get("session_id")
    if session_id is None:
        raise ValueError("session_id is required")

    if config.storage_backend == "juicefs_sdk":
        from ..config_scope_data_model import resolve_file_ops_scope
        scope = config.tool_scope or resolve_file_ops_scope(scope_def)
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

    tool = DeleteItemTool(config=config, storage_backend=storage_backend)

    return (DELETE_ITEM_GENERATION_TOOL_PARAM, tool)


CONSTRUCTOR = {TOOL_NAME: construct_delete_item}