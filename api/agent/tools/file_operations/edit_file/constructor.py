"""
edit_file 工具的实现
"""

import re
from typing import Any

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure, ToolTaskResult
from api.juiceFS.client_worker.exceptions import (
    TaskExecutionError, TaskTimeoutError, WorkerPoolError
)
from ..file_hash_tracker import FileHashNotFoundError, FileHashMismatchError
from .config_data_model import (
    EditFileConfig,
    EditFileParamDefine,
    EDIT_FILE_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
from .types import (
    AnchorParseError,
    EditAction,
    EditAnchorOutput,
    EditOp,
    parse_anchor_ref,
)
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend import JuiceFSSdkBackend

# 检测文本开头是否包含 LINE#HASH: 前缀（使用 NIBBLE_STR 字符集）
_LINE_HASH_PREFIX_RE = re.compile(r"\s*\d+#[ZPMQVRWSNKTXJBYH]{3}:")


class EditFileTool(object):
    """EditFile 工具类

    提供锚点驱动的文件编辑功能，支持 replace/append/prepend/replace_text 操作。
    """

    def __init__(self, config: EditFileConfig, storage_backend: FileOperationsStorageBackend):
        self.config = config
        self.storage_backend = storage_backend

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
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
            return ToolTaskResult(str_content="错误：file_path 不能为空", occur_error=True)

        try:
            edit_action = self._build_edit_action(param)
        except AnchorParseError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except ValueError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)

        # 3. 调用存储后端
        try:
            anchor_output = await self.storage_backend.edit_file_v2(
                param.file_path,
                edit_action,
            )
        except TaskExecutionError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except TaskTimeoutError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except WorkerPoolError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except FileHashNotFoundError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except FileHashMismatchError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except AnchorParseError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)
        except ValueError as e:
            return ToolTaskResult(str_content=str(e), occur_error=True)

        # 4. 格式化响应
        response = self._format_response(param.file_path, anchor_output)
        return ToolTaskResult(str_content=response, occur_error=False)

    def _build_edit_action(self, param: EditFileParamDefine) -> EditAction:
        """根据参数构建 EditAction。步骤 1 的核心逻辑。"""
        op = param.op

        if op == EditOp.REPLACE:
            return self._build_replace_action(param)
        elif op == EditOp.APPEND:
            return self._build_append_action(param)
        elif op == EditOp.PREPEND:
            return self._build_prepend_action(param)
        elif op == EditOp.REPLACE_TEXT:
            return self._build_replace_text_action(param)
        else:
            raise ValueError(f"未知的操作类型: {op}")

    def _validate_and_split_lines(self, text: str | None) -> list[str]:
        """校验 lines 参数: 非空且不含 LINE#HASH: 前缀，然后按换行符拆分。"""
        if text is None:
            raise ValueError("lines 不能为空")
        if _LINE_HASH_PREFIX_RE.match(text):
            raise ValueError(
                "lines 内容以 LINE#HASH: 前缀开头，请发送纯文件内容，不要包含渲染前缀"
            )
        return text.split('\n')

    def _build_replace_action(self, param: EditFileParamDefine) -> EditAction:
        if not param.pos:
            raise ValueError("replace 操作需要 pos 参数（锚点引用）")
        lines = self._validate_and_split_lines(param.lines)

        anchor = parse_anchor_ref(param.pos)
        start_line = anchor.line

        end_line = None
        end_hash = None
        if param.end:
            end_anchor = parse_anchor_ref(param.end)
            if end_anchor.line < start_line:
                raise ValueError(
                    f"end 行号 ({end_anchor.line}) 不能小于 pos 行号 ({start_line})"
                )
            end_line = end_anchor.line
            end_hash = end_anchor.hash

        return EditAction(
            op=EditOp.REPLACE,
            start_line=start_line,
            end_line=end_line,
            new_lines=lines,
            pos_hash=anchor.hash,
            end_hash=end_hash,
        )

    def _build_append_action(self, param: EditFileParamDefine) -> EditAction:
        lines = self._validate_and_split_lines(param.lines)

        start_line = None
        pos_hash = None
        if param.pos:
            anchor = parse_anchor_ref(param.pos)
            start_line = anchor.line
            pos_hash = anchor.hash

        return EditAction(
            op=EditOp.APPEND,
            start_line=start_line,
            new_lines=lines,
            pos_hash=pos_hash,
        )

    def _build_prepend_action(self, param: EditFileParamDefine) -> EditAction:
        lines = self._validate_and_split_lines(param.lines)

        start_line = None
        pos_hash = None
        if param.pos:
            anchor = parse_anchor_ref(param.pos)
            start_line = anchor.line
            pos_hash = anchor.hash

        return EditAction(
            op=EditOp.PREPEND,
            start_line=start_line,
            new_lines=lines,
            pos_hash=pos_hash,
        )

    def _build_replace_text_action(self, param: EditFileParamDefine) -> EditAction:
        if not param.oldText:
            raise ValueError("replace_text 操作需要 oldText 参数")
        if param.newText is None:
            raise ValueError("replace_text 操作需要 newText 参数")

        return EditAction(
            op=EditOp.REPLACE_TEXT,
            old_text=param.oldText,
            new_text=param.newText,
            replace_all=param.replace_all,
        )

    def _format_response(self, file_path: str, anchor_output: EditAnchorOutput) -> str:
        """格式化包含 Edit Anchors 的成功响应。"""
        parts = [f"成功编辑文件：{file_path}"]

        parts.append("")
        parts.append(f"--- Edit Anchors {anchor_output.start_line}-{anchor_output.end_line} ---")
        parts.extend(anchor_output.formatted_lines)
        if anchor_output.total_affected > 20:
            parts.append(f"... ({anchor_output.total_affected} lines affected. If need, use read_file for subsequent edits.)")

        return "\n".join(parts)


def construct_edit_file(
    config: EditFileConfig,
    scope_def: dict[str, Any],
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 EditFileTool 实例"""

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

    tool = EditFileTool(config=config, storage_backend=storage_backend)

    # 注入哈希跟踪器
    branch_name: str | None = kwargs.get("branch_name")  # type: ignore
    if branch_name is not None and user_id is not None:
        from ..file_hash_tracker import FileHashTracker
        storage_backend.hash_tracker = FileHashTracker(
            session_id=session_id,
            user_id=user_id,
            branch_name=branch_name,
        )

    return (
        EDIT_FILE_GENERATION_TOOL_PARAM,
        tool
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_edit_file}
