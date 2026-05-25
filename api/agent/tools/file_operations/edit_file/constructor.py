"""
edit_file 工具的实现
"""

from typing import Any

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

# 导入项目的基础类型
from api.agent.tools.type import ToolClosure, ToolTaskResult
from api.juiceFS.client_worker.exceptions import (
    TaskExecutionError, TaskTimeoutError, WorkerPoolError
)
from .config_data_model import (
    EditFileConfig,
    EditFileParamDefine,
    EDIT_FILE_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
# 导入存储后端
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend import JuiceFSSdkBackend


class EditFileTool(object):
    """
    EditFile 工具类

    提供编辑文件内容的功能，通过替换指定字符串实现。
    支持重复内容检测，确保替换操作的精确性。
    """

    def __init__(self, config: EditFileConfig, storage_backend: FileOperationsStorageBackend):
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
        # 1. 参数验证
        try:
            param = EditFileParamDefine.model_validate(kwargs)
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
        if not param.file_path:
            return ToolTaskResult(
                str_content="错误：file_path 不能为空",
                occur_error=True
            )

        if not param.old_string:
            return ToolTaskResult(
                str_content="错误：old_string 不能为空",
                occur_error=True
            )

        # 3. 调用存储后端编辑文件
        try:
            success, count, updated_content = await self.storage_backend.edit_file(
                param.file_path,
                param.old_string,
                param.new_string,
                param.replace_all
            )
        except TaskExecutionError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except TaskTimeoutError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except WorkerPoolError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except ValueError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)

        # 4. 返回成功结果
        return ToolTaskResult(
            str_content=f"成功编辑文件：{param.file_path}\n替换了 {count} 处内容",
            json_content={
                "action": "edit",
                "file_path": param.file_path,
                "replace_count": count,
                "success": True
            },
            occur_error=False
        )


def construct_edit_file(
    config: EditFileConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 EditFileTool 实例

    Args:
        config: 工具配置
        **kwargs: 依赖参数
            - session_id (UUID, 必需): 用于注入到存储后端
            - user_id (UUID, 可选): UserSpaceFileBackend 需要
            - storage_backend (FileOperationsStorageBackend, 可选): 当 config.storage_backend="kwargs_DI" 时必需

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """

    # 1. 提取 session_id（必需）
    from uuid import UUID
    session_id: UUID | None = kwargs.get("session_id")  # type: ignore
    if session_id is None:
        raise ValueError("session_id is required")

    # 2. 提取 user_id（某些后端需要）
    user_id: UUID | None = kwargs.get("user_id_for_scope")  # type: ignore

    # 3. 根据 config.storage_backend 创建存储后端
    if config.storage_backend == "juicefs_sdk":
        if user_id is None:
            raise ValueError(
                "user_id is required when config.storage_backend='juicefs_sdk'"
            )
        allowed_rel_dirs_in_juicefs_for_tool = kwargs.get("allowed_rel_dirs_in_juicefs_for_tool")  # type: ignore
        storage_backend = JuiceFSSdkBackend(
            session_id=session_id,
            user_id=user_id,
            allowed_rel_dirs_in_juicefs_for_tool=allowed_rel_dirs_in_juicefs_for_tool,
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
    tool = EditFileTool(config=config, storage_backend=storage_backend)

    # 5. 返回工具定义和闭包
    return (
        EDIT_FILE_GENERATION_TOOL_PARAM,
        tool
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_edit_file}
