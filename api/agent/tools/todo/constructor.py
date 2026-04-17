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
    TodoItem,
    TODO_WRITE_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
from .storage_backend.base import TodoStorageBackend
from .todo_model import TodoModel


class TodoWriteTool(object):
    """
    TODO Write 工具类

    提供 TODO 的创建、更新、删除功能。
    支持单个和批量操作，每个 Todo 项可独立设置属性。
    批量操作使用全量读写模式，DB 调用复杂度为 O(1)。

    Attributes:
        config: 工具配置
        storage_backend: 存储后端实例
    """

    def __init__(self, config: TodoWriteConfig, storage_backend: TodoStorageBackend):
        self.config = config
        self.storage_backend = storage_backend

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 1. 参数验证
        try:
            param = TodoWriteParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}",
                occur_error=True
            )

        # 2. 标准化（strip titles）
        self._normalize_items(param)

        # 3. 业务逻辑验证（纯内存，无 DB 调用）
        validation_error = self._validate_parameters(param)
        if validation_error:
            return ToolTaskResult(str_content=validation_error, occur_error=True)

        # 4. Action 分发
        dispatch = {
            "create": self._batch_create,
            "update": self._batch_update,
            "delete": self._batch_delete,
        }

        handler = dispatch.get(param.action)
        if handler is None:
            return ToolTaskResult(str_content=f"未知操作：{param.action}", occur_error=True)

        try:
            return await handler(param.todos)
        except Exception as e:
            return ToolTaskResult(str_content=f"操作失败：{str(e)}", occur_error=True)

    def _normalize_items(self, param: TodoWriteParamDefine) -> None:
        """就地 strip 所有 item 的 title"""
        for item in param.todos:
            item.title = item.title.strip()

    def _validate_parameters(self, param: TodoWriteParamDefine) -> str | None:
        """纯内存验证，无 DB 调用"""
        items = param.todos

        if not items:
            return "错误：todos 列表不能为空"

        for item in items:
            if not item.title:
                return "错误：title 不能为空字符串或只包含空白字符"

        # 检查同一请求中的重复 title
        seen: set[str] = set()
        for item in items:
            if item.title in seen:
                return f"错误：请求中存在重复的 title '{item.title}'"
            seen.add(item.title)

        # update 操作：每个 item 至少需要一个可更新字段
        if param.action == "update":
            for item in items:
                if item.status is None and item.priority is None and item.description is None:
                    return f"错误：update 操作中 '{item.title}' 需要提供 status、priority 或 description"

        return None

    async def _batch_create(self, items: list[TodoItem]) -> ToolTaskResult:
        """批量创建：读全量 → 内存处理 → 写全量"""
        # 1. 读全量（1 DB 读）
        existing_todos = await self.storage_backend.get_all_todos()
        todo_map: dict[str, TodoModel] = {t.title: t for t in existing_todos}

        # 2. 内存中逐项验证和处理
        results: list[dict[str, Any]] = []
        modified = False
        now = datetime.now(timezone.utc).isoformat()

        for item in items:
            if item.title in todo_map:
                results.append({"title": item.title, "success": False, "error": f"Todo '{item.title}' 已存在"})
                continue

            todo = TodoModel(
                title=item.title,
                status=item.status or "pending",
                priority=item.priority or 0,
                description=item.description,
            )
            todo_map[item.title] = todo
            modified = True
            results.append({"title": item.title, "success": True, "message": f"已创建 Todo：{item.title}"})

        # 3. 写全量（1 DB 读 + 1 DB 写）
        if modified:
            await self.storage_backend.save_all_todos(list(todo_map.values()))

        return self._build_result("create", results)

    async def _batch_update(self, items: list[TodoItem]) -> ToolTaskResult:
        """批量更新：读全量 → 内存处理 → 写全量"""
        existing_todos = await self.storage_backend.get_all_todos()
        todo_map: dict[str, TodoModel] = {t.title: t for t in existing_todos}

        results: list[dict[str, Any]] = []
        modified = False
        now = datetime.now(timezone.utc).isoformat()

        for item in items:
            existing = todo_map.get(item.title)
            if existing is None:
                results.append({"title": item.title, "success": False, "error": f"Todo '{item.title}' 不存在"})
                continue

            # 状态流转验证
            if item.status is not None and self.config.enforce_status_transitions:
                if not self._is_valid_status_transition(existing.status, item.status):
                    results.append({
                        "title": item.title, "success": False,
                        "error": f"无效的状态流转：{existing.status} → {item.status}"
                    })
                    continue

            # 应用更新（构造新 TodoModel 以确保数据合法性）
            update_data = existing.model_dump()
            if item.status is not None:
                update_data["status"] = item.status
            if item.priority is not None:
                update_data["priority"] = item.priority
            if item.description is not None:
                update_data["description"] = item.description
            update_data["updated_at"] = now

            todo_map[item.title] = TodoModel(**update_data)
            modified = True
            results.append({"title": item.title, "success": True, "message": f"已更新 Todo：{item.title}"})

        if modified:
            await self.storage_backend.save_all_todos(list(todo_map.values()))

        return self._build_result("update", results)

    async def _batch_delete(self, items: list[TodoItem]) -> ToolTaskResult:
        """批量删除：读全量 → 内存处理 → 写全量"""
        existing_todos = await self.storage_backend.get_all_todos()
        todo_map: dict[str, TodoModel] = {t.title: t for t in existing_todos}

        results: list[dict[str, Any]] = []
        modified = False

        for item in items:
            if item.title not in todo_map:
                results.append({"title": item.title, "success": False, "error": f"Todo '{item.title}' 不存在"})
                continue

            del todo_map[item.title]
            modified = True
            results.append({"title": item.title, "success": True, "message": f"已删除 Todo：{item.title}"})

        if modified:
            await self.storage_backend.save_all_todos(list(todo_map.values()))

        return self._build_result("delete", results)

    def _build_result(self, action: str, results: list[dict[str, Any]]) -> ToolTaskResult:
        """统一构建 ToolTaskResult"""
        success_count = sum(1 for r in results if r["success"])
        failure_count = len(results) - success_count

        # 单项成功：简洁消息
        if len(results) == 1 and success_count == 1:
            return ToolTaskResult(
                str_content=results[0]["message"],
                json_content={"action": action, "title": results[0]["title"], "success": True},
                occur_error=False,
            )

        # 批量或部分失败：汇总
        return ToolTaskResult(
            str_content=self._format_batch_result(action, success_count, failure_count, results),
            json_content={
                "action": action,
                "total_count": len(results),
                "success_count": success_count,
                "failure_count": failure_count,
                "results": results,
            },
            occur_error=(failure_count > 0),
        )

    def _format_batch_result(
        self,
        action: str,
        success_count: int,
        failure_count: int,
        results: list[dict[str, Any]],
    ) -> str:
        action_names = {"create": "创建", "update": "更新", "delete": "删除"}
        action_name = action_names.get(action, action)

        lines = [
            f"批量{action_name}操作完成：",
            f"  总数：{success_count + failure_count}",
            f"  成功：{success_count}",
            f"  失败：{failure_count}",
        ]

        if failure_count > 0:
            lines.append("\n失败详情：")
            for result in results:
                if not result["success"]:
                    lines.append(f"  - {result['title']}: {result.get('error', '未知错误')}")

        return "\n".join(lines)

    def _is_valid_status_transition(self, old_status: str, new_status: str) -> bool:
        valid_transitions = {
            "pending": ["completed"],
            "completed": [],
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
        from .storage_backend.storage_snapshot import StorageSnapshotTodoBackend
        session_task_id: UUID | None = kwargs.get("session_task_id")  # type: ignore
        if session_task_id is None:
            raise ValueError("session_task_id is required for storage_snapshot backend")
        storage_backend = StorageSnapshotTodoBackend(task_id=session_task_id)
        await storage_backend._initialize()

    elif config.storage_backend == "session_storage":
        from .storage_backend.session_storage import SessionStorageTodoBackend
        session_id: UUID | None = kwargs.get("session_id")  # type: ignore
        if session_id is None:
            raise ValueError("session_id is required for session_storage backend")
        storage_backend = SessionStorageTodoBackend(session_id=session_id)

    elif config.storage_backend == "memory":
        from .storage_backend.memory import MemoryTodoBackend
        session_id: UUID | None = kwargs.get("session_id")  # type: ignore
        if session_id is None:
            raise ValueError("session_id is required for memory backend")
        storage_backend = MemoryTodoBackend(session_id=session_id)

    elif config.storage_backend == "local":
        from .storage_backend.local import LocalTodoBackend
        base_path = config.local_base_path or "/tmp/todo_storage"
        storage_backend = LocalTodoBackend(base_path=base_path)

    elif config.storage_backend == "kwargs_DI":
        storage_backend: TodoStorageBackend | None = kwargs.get("storage_backend")  # type: ignore

        if storage_backend is None:
            raise ValueError(
                "storage_backend must be provided in kwargs "
                "when config.storage_backend='kwargs_DI'"
            )

        if not isinstance(storage_backend, TodoStorageBackend):
            raise TypeError(
                f"storage_backend must be an instance of TodoStorageBackend, "
                f"got {type(storage_backend).__name__}"
            )

    else:
        raise ValueError(f"Unknown storage_backend type: {config.storage_backend}")

    tool = TodoWriteTool(config=config, storage_backend=storage_backend)

    return (
        TODO_WRITE_GENERATION_TOOL_PARAM,
        tool
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_todo_write}
