"""
TODO Write 工具的实现
"""

from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

# 导入项目的基础类型
from api.agent.tools.type import ToolClosure, ToolTaskResult
from .config_data_model import (
    TodoWriteConfig,
    TodoWriteParamDefine,
    TODO_WRITE_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
from .storage_backend.base import TodoStorageBackend


class TodoWriteTool(object):
    """
    TODO Write 工具类

    提供 TODO 的创建、更新、删除功能。
    不提供读取功能（读取由其他机制负责）。

    Attributes:
        config: 工具配置
        storage_backend: 存储后端实例
    """

    def __init__(self, config: TodoWriteConfig, storage_backend: TodoStorageBackend):
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
            param = TodoWriteParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}",
                occur_error=True
            )

        # 2. 业务逻辑验证
        validation_error = self._validate_parameters(param)
        if validation_error:
            return ToolTaskResult(
                str_content=validation_error,
                occur_error=True
            )

        # 3. Action 分发
        try:
            if param.action == "create":
                return await self._create_todo(param)
            elif param.action == "update":
                return await self._update_todo(param)
            elif param.action == "delete":
                return await self._delete_todo(param)
            else:
                return ToolTaskResult(
                    str_content=f"未知操作：{param.action}",
                    occur_error=True
                )
        except Exception as e:
            return ToolTaskResult(
                str_content=f"操作失败：{str(e)}",
                occur_error=True
            )

    def _validate_parameters(self, param: TodoWriteParamDefine) -> str | None:
        """
        验证参数的业务逻辑

        Args:
            param: 已验证的参数对象

        Returns:
            如果验证失败返回错误消息，否则返回 None
        """
        if param.action == "create" and not param.title:
            return "错误：create 操作需要提供 'title' 参数"

        if param.action in ["update", "delete"] and not param.todo_id:
            return f"错误：{param.action} 操作需要提供 'todo_id' 参数"

        return None

    async def _create_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
        """
        创建新的 Todo

        Args:
            param: 参数对象

        Returns:
            ToolTaskResult: 创建结果
        """
        # 1. 生成 UUID 和时间戳
        todo_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # 2. 构造 todo_data
        todo_data = {
            "id": todo_id,
            "title": param.title,
            "status": param.status or "pending",
            "priority": param.priority or 0,
            "created_at": now,
            "updated_at": now
        }

        # 3. 调用存储后端创建
        try:
            created_id = await self.storage_backend.create_todo(todo_data)
        except Exception as e:
            return ToolTaskResult(
                str_content=f"创建 Todo 失败：{str(e)}",
                occur_error=True
            )

        # 4. 返回成功结果
        return ToolTaskResult(
            str_content=f"已创建 Todo，ID：{created_id}",
            json_content={
                "action": "create",
                "todo_id": created_id,
                "success": True
            },
            occur_error=False
        )

    async def _update_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
        """
        更新 Todo

        Args:
            param: 参数对象

        Returns:
            ToolTaskResult: 更新结果
        """
        # 1. 先验证 Todo 是否存在
        # 类型断言：_validate_parameters 已确保 param.todo_id 不为 None
        todo_id = param.todo_id
        assert todo_id is not None, "todo_id must not be None for update operation"

        existing = await self.storage_backend.get_todo(todo_id)
        if existing is None:
            return ToolTaskResult(
                str_content=f"Todo '{todo_id}' 不存在",
                occur_error=True
            )

        # 2. 构造更新数据
        updates = {}

        if param.title is not None:
            updates["title"] = param.title
        if param.status is not None:
            # 验证状态流转（如果配置要求）
            if self.config.enforce_status_transitions:
                if not self._is_valid_status_transition(existing["status"], param.status):
                    return ToolTaskResult(
                        str_content=f"无效的状态流转：{existing['status']} → {param.status}",
                        occur_error=True
                    )
            updates["status"] = param.status
        if param.priority is not None:
            updates["priority"] = param.priority

        # 更新时间戳
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        # 3. 调用存储后端更新
        try:
            success = await self.storage_backend.update_todo(todo_id, updates)
            if not success:
                return ToolTaskResult(
                    str_content=f"更新 Todo '{todo_id}' 失败",
                    occur_error=True
                )
        except Exception as e:
            return ToolTaskResult(
                str_content=f"更新 Todo 失败：{str(e)}",
                occur_error=True
            )

        # 4. 返回成功结果
        return ToolTaskResult(
            str_content=f"已更新 Todo '{todo_id}'",
            json_content={
                "action": "update",
                "todo_id": todo_id,
                "success": True
            },
            occur_error=False
        )

    async def _delete_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
        """
        删除 Todo

        Args:
            param: 参数对象

        Returns:
            ToolTaskResult: 删除结果
        """
        # 1. 先验证 Todo 是否存在
        # 类型断言：_validate_parameters 已确保 param.todo_id 不为 None
        todo_id = param.todo_id
        assert todo_id is not None, "todo_id must not be None for delete operation"

        existing = await self.storage_backend.get_todo(todo_id)
        if existing is None:
            return ToolTaskResult(
                str_content=f"Todo '{todo_id}' 不存在",
                occur_error=True
            )

        # 2. 调用存储后端删除
        try:
            success = await self.storage_backend.delete_todo(todo_id)
            if not success:
                return ToolTaskResult(
                    str_content=f"删除 Todo '{todo_id}' 失败",
                    occur_error=True
                )
        except Exception as e:
            return ToolTaskResult(
                str_content=f"删除 Todo 失败：{str(e)}",
                occur_error=True
            )

        # 3. 返回成功结果
        return ToolTaskResult(
            str_content=f"已删除 Todo '{todo_id}'",
            json_content={
                "action": "delete",
                "todo_id": todo_id,
                "success": True
            },
            occur_error=False
        )

    def _is_valid_status_transition(self, old_status: str, new_status: str) -> bool:
        """
        验证状态流转是否合法

        Args:
            old_status: 当前状态
            new_status: 目标状态

        Returns:
            如果流转合法返回 True，否则返回 False
        """
        valid_transitions = {
            "pending": ["in_progress", "cancelled"],
            "in_progress": ["completed", "cancelled"],
            "completed": [],  # 终态
            "cancelled": []   # 终态
        }
        return new_status in valid_transitions.get(old_status, [])


def construct_todo_write(
    config: TodoWriteConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 TodoWriteTool 实例

    Args:
        config: 工具配置
        **kwargs: 依赖参数
            - session_id (UUID, 必需): 用于注入到存储后端
            - storage_backend (TodoStorageBackend, 可选): 当 config.storage_backend="kwargs_DI" 时必需

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """

    # 1. 提取 session_id（必需）
    session_id: UUID | None = kwargs.get("session_id")  # type: ignore
    if session_id is None:
        raise ValueError("session_id is required")

    # 2. 根据 config.storage_backend 创建存储后端
    if config.storage_backend == "session_storage":
        # 模式 1: Session Storage
        from .storage_backend.session_storage import SessionStorageTodoBackend
        storage_backend = SessionStorageTodoBackend(session_id=session_id)

    elif config.storage_backend == "memory":
        # 模式 2: Memory Storage
        from .storage_backend.memory import MemoryTodoBackend
        storage_backend = MemoryTodoBackend(session_id=session_id)

    elif config.storage_backend == "kwargs_DI":
        # 模式 3: 依赖注入
        storage_backend: TodoStorageBackend | None = kwargs.get("storage_backend")  # type: ignore

        if storage_backend is None:
            raise ValueError(
                "storage_backend must be provided in kwargs "
                "when config.storage_backend='kwargs_DI'"
            )

        # 类型验证
        if not isinstance(storage_backend, TodoStorageBackend):
            raise TypeError(
                f"storage_backend must be an instance of TodoStorageBackend, "
                f"got {type(storage_backend).__name__}"
            )

    else:
        # 不应该到达这里（Pydantic 会验证 config.storage_backend）
        raise ValueError(f"Unknown storage_backend type: {config.storage_backend}")

    # 3. 创建工具实例
    tool = TodoWriteTool(config=config, storage_backend=storage_backend)

    # 4. 返回工具定义和闭包
    return (
        TODO_WRITE_GENERATION_TOOL_PARAM,
        tool
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_todo_write}
