"""
TODO 工具的生命周期钩子

提供在 Agent 启动时自动注入 TODO 上下文的功能。
"""

from typing import TYPE_CHECKING
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_system_message_param import ChatCompletionSystemMessageParam
from openai.types.chat.chat_completion_user_message_param import ChatCompletionUserMessageParam

from api.agent.life_cycle_decorators import lifecycle_hook
from .todo_model import TodoModel
from .config_data_model import TOOL_NAME as TODO_TOOL_NAME

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


@lifecycle_hook('on_agent_start', position='before')
async def inject_todo_context_on_agent_start(
    self: "AgentBase",
    memories: list[ChatCompletionMessageParam]
) -> None:
    await inject_todo_context(self)
    
@lifecycle_hook('on_iteration_end', position='before')
async def inject_todo_context_on_iteration_end(
    self: "AgentBase",
    iteration: int,
    memories: list[ChatCompletionMessageParam]
) -> None:
    # 找到 self._runtime_memories 中的最后一个assisiant消息，如果存在对 TODO 工具的 tool_call，则注入 TODO 列表
    last_assistant_message = None
    for m in reversed(self._runtime_memories):
        if m["role"] == "assistant":
            last_assistant_message = m
            break
    if not last_assistant_message or not ( tool_calls := last_assistant_message.get("tool_calls")):
        return
    has_todo_write_tool_call = False
    for tool_call in tool_calls:
        if tool_call["function"]["name"] == TODO_TOOL_NAME:
            has_todo_write_tool_call = True
            break
    if not has_todo_write_tool_call:
        return
    
    await inject_todo_context(self)

async def inject_todo_context(
    self: "AgentBase"
) -> None:
    """
    注入 TODO 列表到 Agent 记忆中

    功能：
    1. 检查 TODO 工具是否已加载
    2. 检查是否应该注入（防止重复注入）
    3. 从存储后端读取所有 TODO 项
    4. 格式化 TODO 列表
    5. 将格式化后的内容作为assisiant消息添加到 _runtime_memories 和 _new_memories
    """
    # 1. 检查 TODO 工具是否被加载
    if TODO_TOOL_NAME not in self.tool_call_function:
        return

    # 2. 检查是否应该注入
    if not _should_inject_todo_context(self._runtime_memories):
        return

    # 3. 获取 TODO 工具实例
    todo_tool = self.tool_call_function[TODO_TOOL_NAME]

    # 4. 类型安全检查
    if not hasattr(todo_tool, 'storage_backend'):
        return

    # 5. 从存储后端读取 TODO 列表（静默失败）
    try:
        todos = await todo_tool.storage_backend.get_all_todos()
    except Exception:
        return

    # 6. 如果没有 TODO，直接返回
    if not todos:
        return

    # 7. 格式化 TODO 列表
    formatted_todos = _format_todos_for_context(todos)

    # 8. 创建用户消息并添加到 memories
    todo_context_message = ChatCompletionSystemMessageParam(
        role="system",
        content=formatted_todos
    )
    self._runtime_memories.append(todo_context_message)
    self._new_memories.append(todo_context_message)


def _should_inject_todo_context(memories: list[ChatCompletionMessageParam]) -> bool:
    """
    检查是否应该注入 TODO 上下文

    目前总是返回 True（允许注入）。
    """
    return True


def _format_todos_for_context(todos: list[TodoModel]) -> str:
    """
    格式化 TODO 列表为适合注入到对话上下文的文本

    格式化策略：
    1. 按状态分组（pending 和 completed）
    2. 每组内按优先级降序排列

    Args:
        todos: TodoModel 列表

    Returns:
        格式化后的 TODO 文本
    """
    # 按状态分组
    status_groups = {
        "pending": [],
        "completed": []
    }

    for todo in todos:
        if todo.status in status_groups:
            status_groups[todo.status].append(todo)

    # 每组按优先级降序排序
    for status in status_groups:
        status_groups[status].sort(key=lambda t: t.priority, reverse=True)

    # 构建格式化文本
    lines = ["<todo_list>\n# 当前任务列表\n"]

    # 待处理任务
    if status_groups["pending"]:
        lines.append("## 待处理")
        for todo in status_groups["pending"]:
            lines.append(f"- {todo.title} (优先级: {todo.priority})")

    # 已完成任务
    if status_groups["completed"]:
        lines.append("\n## 已完成")
        for todo in status_groups["completed"]:
            lines.append(f"- {todo.title}")
    lines.append("<\\todo_list>")

    return "\n".join(lines)