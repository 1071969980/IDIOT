"""
read_file 工具的实现
"""

import asyncio
from typing import Any, cast

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

# 导入项目的基础类型
from api.agent.tools.type import ToolClosure, ToolTaskResult
from api.juiceFS.client_worker.exceptions import (
    TaskExecutionError, TaskTimeoutError, WorkerPoolError, TaskCancelledError,
)
from .config_data_model import (
    ReadFileConfig,
    ReadFileParamDefine,
    READ_FILE_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
# 导入存储后端
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend import JuiceFSSdkBackend


class ReadFileTool(object):
    """
    ReadFile 工具类

    提供读取文件内容的功能，支持偏移量、行数限制和行号显示。
    """

    def __init__(self, config: ReadFileConfig, storage_backend: FileOperationsStorageBackend):
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

        # 快速返回：已被取消
        if cancel_event and cancel_event.is_set():
            return ToolTaskResult(
                str_content="文件读取已被用户取消",
                occur_error=True,
            )

        # 1. 参数验证
        try:
            param = ReadFileParamDefine.model_validate(kwargs)
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

        if param.offset is not None and param.offset < 0:
            return ToolTaskResult(
                str_content="错误：offset 必须大于等于 0",
                occur_error=True
            )

        if param.limit is not None and param.limit <= 0:
            return ToolTaskResult(
                str_content="错误：limit 必须大于 0",
                occur_error=True
            )

        # 3. 调用存储后端读取文件
        try:
            content, first_line, total_lines = await self.storage_backend.read_file(
                param.file_path,
                param.offset,
                param.limit,
                record_hash=True,
                cancel_event=cancel_event,
            )
        except TaskCancelledError:
            return ToolTaskResult(
                str_content="文件读取已被用户取消",
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

        # 4. 格式化输出（自动添加行号和截断长行）
        formatted_content = self._format_output(
            content,
            param.file_path,
            first_line,
            total_lines
        )

        return ToolTaskResult(
            str_content=formatted_content,
            occur_error=False
        )

    def _format_output(
        self,
        content: str,
        file_path: str,
        first_line_number: int,
        total_lines: int
    ) -> str:
        """格式化输出内容为 LINE#HASH:CONTENT 格式。

        每行输出格式: <右对齐行号>#<3字符哈希>:<内容>
        长行超过 1000 字符时截断。
        """
        from ..line_hash import compute_line_hash

        lines = content.split('\n')

        # 处理空文件
        if not lines or (len(lines) == 1 and not lines[0]):
            return f"文件内容：{file_path}\n文件为空"

        # 右对齐宽度由实际显示的最大行号决定
        last_line_number = first_line_number + len(lines) - 1
        width = len(str(last_line_number))

        # 格式化每一行
        formatted_lines = []
        for i, line in enumerate(lines):
            # 哈希基于原始行内容（截断前计算，确保与 edit 锚点验证一致）
            hash_str = compute_line_hash(line)

            # 截断长行（仅影响显示，不影响哈希）
            if len(line) > 1000:
                line = line[:1000] + "... [line be truncated]"

            line_number = i + first_line_number
            formatted_lines.append(f"{str(line_number).rjust(width)}#{hash_str}:{line}")

        formatted_content = '\n'.join(formatted_lines)

        # 计算实际读取的行数
        lines_count = len(lines)
        last_line_number = first_line_number + lines_count - 1 if lines_count > 0 else first_line_number

        header = (
            f"文件内容：{file_path}\n"
            f"读取行数：{first_line_number}-{last_line_number} / 共{total_lines}行\n"
        )

        return header + "\n" + formatted_content


def construct_read_file(
    config: ReadFileConfig,
    scope_def: dict[str, Any],
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 ReadFileTool 实例

    Args:
        config: 工具配置
        scope_def: 作用域定义字典
        **kwargs: 依赖参数

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """

    from uuid import UUID
    session_id: UUID | None = kwargs.get("session_id")  # type: ignore
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
        user_id = scope.user_id_for_scope

    elif config.storage_backend == "kwargs_DI":
        storage_backend: FileOperationsStorageBackend | None = kwargs.get("storage_backend")  # type: ignore
        user_id: UUID | None = kwargs.get("user_id_for_scope")  # type: ignore

        if storage_backend is None:
            raise ValueError(
                "storage_backend must be provided in kwargs "
                "when config.storage_backend='kwargs_DI'"
            )

        if not isinstance(storage_backend, FileOperationsStorageBackend):
            raise TypeError(
                f"storage_backend must be an instance of FileOperationsStorageBackend, "
                f"got {type(storage_backend).__name__}"
            )

    else:
        raise ValueError(f"Unknown storage_backend type: {config.storage_backend}")

    tool = ReadFileTool(config=config, storage_backend=storage_backend)

    branch_name: str | None = kwargs.get("branch_name")  # type: ignore
    if branch_name is not None and user_id is not None:
        from ..file_hash_tracker import FileHashTracker
        storage_backend.hash_tracker = FileHashTracker(
            session_id=session_id,
            user_id=user_id,
            branch_name=branch_name,
        )

    return (
        READ_FILE_GENERATION_TOOL_PARAM,
        tool
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_read_file}
