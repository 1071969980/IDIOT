"""
TODO Write 工具的实现
"""

from uuid import UUID
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
from .todo_model import TodoModel


class TodoWriteTool(object):
    """
    TODO Write 工具类

    提供 TODO 的创建、更新、删除功能。
    支持单个和批量操作。

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
        # 验证 title 参数
        if not param.title:
            return "错误：title 参数不能为空"

        # 标准化为列表（统一处理单个和批量），同时进行 strip 处理
        titles = self._normalize_titles(param.title)

        # 验证标题列表不为空（strip 后可能变为空字符串）
        if not titles or len(titles) == 0:
            return "错误：title 列表不能为空"

        # 验证标题不为空字符串（strip 后）
        for title in titles:
            if not title:
                return "错误：title 不能为空字符串或只包含空白字符"

        # update 操作：验证 status 和 priority 至少有一个
        if param.action == "update":
            if param.status is None and param.priority is None:
                return "错误：update 操作需要提供 status 或 priority 参数"

        return None

    def _normalize_titles(self, title: str | list[str]) -> list[str]:
        """
        将 title 标准化为列表，并对每个 title 进行 strip 处理

        Args:
            title: 单个标题或标题列表

        Returns:
            strip 后的标题列表
        """
        if isinstance(title, str):
            return [title.strip()]
        return [t.strip() for t in title]

    async def _create_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
        """
        创建新的 Todo（支持批量）

        Args:
            param: 参数对象

        Returns:
            ToolTaskResult: 创建结果
        """
        # 1. 标准化为列表
        titles = self._normalize_titles(param.title)

        # 2. 单个操作：直接处理
        if len(titles) == 1:
            title = titles[0]
            now = datetime.now(timezone.utc).isoformat()

            try:
                # 检查 title 是否已存在
                existing = await self.storage_backend.get_todo(title)
                if existing is not None:
                    return ToolTaskResult(
                        str_content=f"Todo '{title}' 已存在",
                        occur_error=True
                    )

                # 创建 Todo
                todo = TodoModel(
                    title=title,
                    status=param.status or "pending",
                    priority=param.priority or 0,
                    created_at=now,
                    updated_at=now
                )

                created_title = await self.storage_backend.create_todo(todo)
                return ToolTaskResult(
                    str_content=f"已创建 Todo：{created_title}",
                    json_content={
                        "action": "create",
                        "title": created_title,
                        "success": True
                    },
                    occur_error=False
                )
            except Exception as e:
                return ToolTaskResult(
                    str_content=f"创建 Todo 失败：{str(e)}",
                    occur_error=True
                )

        # 3. 批量操作：循环处理
        results = []
        now = datetime.now(timezone.utc).isoformat()

        for title in titles:
            try:
                # 检查 title 是否已存在
                existing = await self.storage_backend.get_todo(title)
                if existing is not None:
                    results.append({
                        "title": title,
                        "success": False,
                        "error": f"Todo '{title}' 已存在"
                    })
                    continue

                # 创建 Todo
                todo = TodoModel(
                    title=title,
                    status=param.status or "pending",
                    priority=param.priority or 0,
                    created_at=now,
                    updated_at=now
                )

                created_title = await self.storage_backend.create_todo(todo)
                results.append({
                    "title": created_title,
                    "success": True
                })

            except Exception as e:
                results.append({
                    "title": title,
                    "success": False,
                    "error": str(e)
                })

        # 4. 统计结果
        success_count = sum(1 for r in results if r["success"])
        failure_count = len(results) - success_count

        # 5. 返回汇总结果
        return ToolTaskResult(
            str_content=self._format_batch_result("create", success_count, failure_count, results),
            json_content={
                "action": "create",
                "total_count": len(titles),
                "success_count": success_count,
                "failure_count": failure_count,
                "results": results
            },
            occur_error=(failure_count > 0)
        )

    async def _update_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
        """
        更新 Todo（支持批量）

        Args:
            param: 参数对象

        Returns:
            ToolTaskResult: 更新结果
        """
        # 1. 标准化为列表
        titles = self._normalize_titles(param.title)

        # 2. 构造更新数据
        updates = {}
        if param.status is not None:
            updates["status"] = param.status
        if param.priority is not None:
            updates["priority"] = param.priority
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        # 3. 单个操作：直接处理
        if len(titles) == 1:
            title = titles[0]

            # 检查 Todo 是否存在
            existing = await self.storage_backend.get_todo(title)
            if existing is None:
                return ToolTaskResult(
                    str_content=f"Todo '{title}' 不存在",
                    occur_error=True
                )

            # 验证状态流转（如果配置要求）
            if "status" in updates and self.config.enforce_status_transitions:
                if not self._is_valid_status_transition(existing.status, updates["status"]):
                    return ToolTaskResult(
                        str_content=f"无效的状态流转：{existing.status} → {updates['status']}",
                        occur_error=True
                    )

            # 执行更新
            try:
                success = await self.storage_backend.update_todo(title, updates)
                if not success:
                    return ToolTaskResult(
                        str_content=f"更新 Todo '{title}' 失败",
                        occur_error=True
                    )
            except Exception as e:
                return ToolTaskResult(
                    str_content=f"更新 Todo 失败：{str(e)}",
                    occur_error=True
                )

            return ToolTaskResult(
                str_content=f"已更新 Todo：{title}",
                json_content={
                    "action": "update",
                    "title": title,
                    "success": True
                },
                occur_error=False
            )

        # 4. 批量操作：循环处理
        results = []

        for title in titles:
            try:
                # 检查 Todo 是否存在
                existing = await self.storage_backend.get_todo(title)
                if existing is None:
                    results.append({
                        "title": title,
                        "success": False,
                        "error": f"Todo '{title}' 不存在"
                    })
                    continue

                # 验证状态流转（如果配置要求）
                if "status" in updates and self.config.enforce_status_transitions:
                    if not self._is_valid_status_transition(existing.status, updates["status"]):
                        results.append({
                            "title": title,
                            "success": False,
                            "error": f"无效的状态流转：{existing.status} → {updates['status']}"
                        })
                        continue

                # 执行更新
                success = await self.storage_backend.update_todo(title, updates)
                if success:
                    results.append({
                        "title": title,
                        "success": True
                    })
                else:
                    results.append({
                        "title": title,
                        "success": False,
                        "error": f"更新 Todo '{title}' 失败"
                    })

            except Exception as e:
                results.append({
                    "title": title,
                    "success": False,
                    "error": str(e)
                })

        # 5. 统计结果
        success_count = sum(1 for r in results if r["success"])
        failure_count = len(results) - success_count

        # 6. 返回汇总结果
        return ToolTaskResult(
            str_content=self._format_batch_result("update", success_count, failure_count, results),
            json_content={
                "action": "update",
                "total_count": len(titles),
                "success_count": success_count,
                "failure_count": failure_count,
                "results": results
            },
            occur_error=(failure_count > 0)
        )

    async def _delete_todo(self, param: TodoWriteParamDefine) -> ToolTaskResult:
        """
        删除 Todo（支持批量）

        Args:
            param: 参数对象

        Returns:
            ToolTaskResult: 删除结果
        """
        # 1. 标准化为列表
        titles = self._normalize_titles(param.title)

        # 2. 单个操作：直接处理
        if len(titles) == 1:
            title = titles[0]

            # 检查 Todo 是否存在
            existing = await self.storage_backend.get_todo(title)
            if existing is None:
                return ToolTaskResult(
                    str_content=f"Todo '{title}' 不存在",
                    occur_error=True
                )

            # 执行删除
            try:
                success = await self.storage_backend.delete_todo(title)
                if not success:
                    return ToolTaskResult(
                        str_content=f"删除 Todo '{title}' 失败",
                        occur_error=True
                    )
            except Exception as e:
                return ToolTaskResult(
                    str_content=f"删除 Todo 失败：{str(e)}",
                    occur_error=True
                )

            return ToolTaskResult(
                str_content=f"已删除 Todo：{title}",
                json_content={
                    "action": "delete",
                    "title": title,
                    "success": True
                },
                occur_error=False
            )

        # 3. 批量操作：循环处理
        results = []

        for title in titles:
            try:
                # 检查 Todo 是否存在
                existing = await self.storage_backend.get_todo(title)
                if existing is None:
                    results.append({
                        "title": title,
                        "success": False,
                        "error": f"Todo '{title}' 不存在"
                    })
                    continue

                # 执行删除
                success = await self.storage_backend.delete_todo(title)
                if success:
                    results.append({
                        "title": title,
                        "success": True
                    })
                else:
                    results.append({
                        "title": title,
                        "success": False,
                        "error": f"删除 Todo '{title}' 失败"
                    })

            except Exception as e:
                results.append({
                    "title": title,
                    "success": False,
                    "error": str(e)
                })

        # 4. 统计结果
        success_count = sum(1 for r in results if r["success"])
        failure_count = len(results) - success_count

        # 5. 返回汇总结果
        return ToolTaskResult(
            str_content=self._format_batch_result("delete", success_count, failure_count, results),
            json_content={
                "action": "delete",
                "total_count": len(titles),
                "success_count": success_count,
                "failure_count": failure_count,
                "results": results
            },
            occur_error=(failure_count > 0)
        )

    def _format_batch_result(
        self,
        action: str,
        success_count: int,
        failure_count: int,
        results: list[dict[str, Any]]
    ) -> str:
        """
        格式化批量操作结果

        Args:
            action: 操作类型
            success_count: 成功数量
            failure_count: 失败数量
            results: 详细结果列表

        Returns:
            格式化的结果字符串
        """
        action_names = {
            "create": "创建",
            "update": "更新",
            "delete": "删除"
        }
        action_name = action_names.get(action, action)

        lines = [
            f"批量{action_name}操作完成：",
            f"  总数：{success_count + failure_count}",
            f"  成功：{success_count}",
            f"  失败：{failure_count}"
        ]

        # 如果有失败的，列出失败项
        if failure_count > 0:
            lines.append("\n失败详情：")
            for result in results:
                if not result["success"]:
                    lines.append(f"  - {result['title']}: {result.get('error', '未知错误')}")

        return "\n".join(lines)

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
            "pending": ["completed"],
            "completed": []  # 终态
        }
        return new_status in valid_transitions.get(old_status, [])


async def construct_todo_write(
    config: TodoWriteConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 TodoWriteTool 实例

    Args:
        config: 工具配置
        **kwargs: 依赖参数
            - session_task_id (UUID, 可选): 用于 storage_snapshot 后端
            - session_id (UUID, 可选): 用于 session_storage/memory 后端
            - storage_backend (TodoStorageBackend, 可选): 当 config.storage_backend="kwargs_DI" 时必需

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """

    # 根据 config.storage_backend 创建存储后端
    if config.storage_backend == "storage_snapshot":
        # 模式 0: Storage Snapshot（需要 session_task_id，默认）
        from .storage_backend.storage_snapshot import StorageSnapshotTodoBackend
        session_task_id: UUID | None = kwargs.get("session_task_id")  # type: ignore
        if session_task_id is None:
            raise ValueError("session_task_id is required for storage_snapshot backend")
        storage_backend = StorageSnapshotTodoBackend(task_id=session_task_id)
        await storage_backend._initialize()

    elif config.storage_backend == "session_storage":
        # 模式 1: Session Storage（需要 session_id）
        from .storage_backend.session_storage import SessionStorageTodoBackend
        session_id: UUID | None = kwargs.get("session_id")  # type: ignore
        if session_id is None:
            raise ValueError("session_id is required for session_storage backend")
        storage_backend = SessionStorageTodoBackend(session_id=session_id)

    elif config.storage_backend == "memory":
        # 模式 2: Memory Storage（需要 session_id）
        from .storage_backend.memory import MemoryTodoBackend
        session_id: UUID | None = kwargs.get("session_id")  # type: ignore
        if session_id is None:
            raise ValueError("session_id is required for memory backend")
        storage_backend = MemoryTodoBackend(session_id=session_id)

    elif config.storage_backend == "local":
        # 模式 3: Local Storage（不需要 session_id）
        from .storage_backend.local import LocalTodoBackend
        base_path = config.local_base_path or "/tmp/todo_storage"
        storage_backend = LocalTodoBackend(base_path=base_path)

    elif config.storage_backend == "kwargs_DI":
        # 模式 4: 依赖注入
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

    # 创建工具实例
    tool = TodoWriteTool(config=config, storage_backend=storage_backend)

    # 返回工具定义和闭包
    return (
        TODO_WRITE_GENERATION_TOOL_PARAM,
        tool
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_todo_write}
