"""
edit_file 工具的实现
"""

from typing import Any

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

# 导入项目的基础类型
from api.agent.tools.type import ToolClosure, ToolTaskResult
from .config_data_model import (
    EditFileConfig,
    EditFileParamDefine,
    EDIT_FILE_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
# 导入存储后端
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend.memory import MemoryFileBackend
from ..storage_backend.local import LocalFileBackend
from ..storage_backend.user_space import UserSpaceFileBackend
from ..storage_backend import UserPodFileBackend, JuiceFSSdkBackend


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
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}",
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
        except FileNotFoundError:
            return ToolTaskResult(
                str_content=f"文件不存在：{param.file_path}",
                occur_error=True
            )
        except ValueError as e:
            # 处理重复内容或未找到内容的错误
            error_msg = str(e)
            if "重复" in error_msg or "未找到" in error_msg:
                return ToolTaskResult(
                    str_content=error_msg,
                    occur_error=True
                )
            return ToolTaskResult(
                str_content=f"参数错误：{error_msg}",
                occur_error=True
            )
        except PermissionError:
            return ToolTaskResult(
                str_content=f"无权限编辑文件：{param.file_path}",
                occur_error=True
            )
        except Exception as e:
            return ToolTaskResult(
                str_content=f"编辑文件时发生错误：{str(e)}",
                occur_error=True
            )

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
    if config.storage_backend == "memory":
        # 模式 1: Memory Storage
        storage_backend = MemoryFileBackend(session_id=session_id)

    elif config.storage_backend == "local":
        # 模式 2: Local Storage
        base_path = config.local_base_path or "/tmp/file_tools"
        storage_backend = LocalFileBackend(
            session_id=session_id,
            base_path=base_path
        )

    elif config.storage_backend == "user_space":
        # 模式 3: User Space Storage
        if user_id is None:
            raise ValueError(
                "user_id is required when config.storage_backend='user_space'"
            )
        storage_backend = UserSpaceFileBackend(
            session_id=session_id,
            user_id=user_id
        )

    elif config.storage_backend == "user_pod":
        # 模式 3.5: User Pod Storage
        if user_id is None:
            raise ValueError(
                "user_id is required when config.storage_backend='user_pod'"
            )
        storage_backend = UserPodFileBackend(
            session_id=session_id,
            user_id=user_id
        )

    elif config.storage_backend == "juicefs_sdk":
        # 模式 5: JuiceFS SDK Storage
        if user_id is None:
            raise ValueError(
                "user_id is required when config.storage_backend='juicefs_sdk'"
            )
        work_dirs = kwargs.get("work_dirs")  # type: ignore
        storage_backend = JuiceFSSdkBackend(
            session_id=session_id,
            user_id=user_id,
            work_dirs=work_dirs,
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
