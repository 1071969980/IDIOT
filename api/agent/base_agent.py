import asyncio
from abc import ABC
from asyncio import Event, Task
from typing import Any
from uuid import UUID

import ujson
from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaToolCall,
)
from openai.types.chat.chat_completion_message_param import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.completion_usage import CompletionUsage

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.chat.sql_stat.u2a_agent_msg.utils import _U2AAgentMessageCreate
from api.chat.sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryCreate,
)
from api.llm.generator import DEFAULT_RETRY_CONFIG
from api.load_balance import LOAD_BLANCER
from api.load_balance.delegate.openai import generation_delegate_for_async_openai


class AgentBase(ABC):
    """Agent 基类，提供核心 agent 循环功能和生命周期方法。"""

    def __init__(
        self,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        cancel_event: Event,
        tools: list[ChatCompletionToolParam],
        tool_call_function: dict[str, ToolClosure],
        loop_control: Any = None,
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self.cancel_event = cancel_event
        self.tools = tools
        self.tool_call_function = tool_call_function
        self.loop_control = loop_control

        # 内部状态
        self._runtime_memories: list[ChatCompletionAssistantMessageParam | ChatCompletionToolMessageParam] = []
        self._new_agent_memories_create: list[_AgentShortTermMemoryCreate] = []
        self._new_agent_messages_create: list[_U2AAgentMessageCreate] = []
        self._new_agent_msg_sub_seq_index_counter = 0

    async def _execute_tool_calls(
        self,
        tool_calls: list[ChoiceDeltaToolCall],
        tool_call_function: dict[str, ToolClosure],
    ) -> tuple[list[ChatCompletionToolMessageParam], dict[str, Task[ToolTaskResult] | None]]:
        """执行工具调用并返回工具消息参数。"""

        # 提取工具函数和参数
        tool_func = {
            tool_call.function.name: tool_call_function.get(tool_call.function.name)
            for tool_call in tool_calls
        }
        tool_func_params = {
            tool_call.function.name: ujson.loads(tool_call.function.arguments)
            for tool_call in tool_calls
        }

        # 创建任务
        tool_func_task: dict[str, Task[ToolTaskResult] | None] = {
            tool_call.function.name: None
            for tool_call in tool_calls
        }

        # 通知工具调用开始
        await self.on_tool_calls_start_batch(tool_calls, tool_func, tool_func_params)

        for tool_call in tool_calls:
            if tool_func[tool_call.function.name]:
                # 通知单个工具调用开始
                await self.on_tool_call_start(
                    tool_call.function.name,
                    tool_func_params[tool_call.function.name],
                )

                # 使用 asyncio.create_task 创建异步任务
                tool_func_task[tool_call.function.name] = asyncio.create_task(
                    tool_func[tool_call.function.name](
                        **tool_func_params[tool_call.function.name],
                    ),
                )

        # 执行所有工具调用
        done, pending = await asyncio.wait(
            {task for task in tool_func_task.values() if task is not None},
            return_when=asyncio.ALL_COMPLETED,
        )

        # 收集结果并处理每个工具调用的结果
        tool_result : dict[str, str] = {}
        for tool_name, tool_task in tool_func_task.items():
            if tool_task is None:
                result = f"{tool_name} Response : \n{tool_name} can not be called right now"
                tool_result[tool_name] = result
                await self.on_tool_call_error(tool_name, ValueError("Tool function not found"))
            elif hasattr(tool_task, "exception") and (e := tool_task.exception()):
                result = f"{tool_name} Response : \n{tool_name} raised exception : {e!s}"
                tool_result[tool_name] = result
                await self.on_tool_call_error(tool_name, e)
            else:
                tool_result[tool_name] = f"{tool_name} Response : \n{tool_task.result().text}"
                await self.on_tool_call_complete(tool_name, tool_task.result())

        # 创建工具消息参数
        tool_mems = [
            ChatCompletionToolMessageParam(
                content=tool_result[tool_call.function.name],
                role="tool",
                tool_call_id=tool_call.id,
            )
            for tool_call in tool_calls
        ]

        return tool_mems, tool_func_task

    async def run(self, memories: list[ChatCompletionMessageParam], service_name: str) -> tuple[list[_AgentShortTermMemoryCreate], list[_U2AAgentMessageCreate]]:
        """执行 agent 循环。"""
        # Agent 开始
        await self.on_agent_start(memories)

        # agent 循环
        keep_agent_loop = self.loop_flag_init()
        iteration = 0


        # 准备 LLM 请求参数
        kwargs = await self.prepare_kwargs(memories + self._runtime_memories)

        # 准备工具
        tools, tool_call_function = await self.prepare_tools(memories + self._runtime_memories)

        # 如果有工具，添加到 kwargs 中
        if tools:
            kwargs["tools"] = tools

        async def delegate(instance):
            return await generation_delegate_for_async_openai(
                instance,
                memories + self._runtime_memories,
                DEFAULT_RETRY_CONFIG,
                stream=True,
                **kwargs,
            )

        while self.loop_flag_should_continue(keep_agent_loop):
            iteration += 1
            keep_agent_loop = self.loop_flag_unset_on_iter_start(keep_agent_loop, iteration)

            # 循环开始
            await self.on_iteration_start(iteration)

            result = await LOAD_BLANCER.execute(service_name, delegate)

            content_chunks = []

            _tool_calls: list[ChoiceDeltaToolCall] = []

            # 开始生成内容
            await self.on_generate_start()

            # 处理流式响应
            async for chunk in result:
                if chunk.choices[0].delta.tool_calls:
                    _tool_calls += chunk.choices[0].delta.tool_calls
                if chunk.choices[0].delta.content:
                    content_chunks.append(chunk.choices[0].delta.content)
                    await self.on_generate_delta(chunk.choices[0].delta.content)
                    await self.record_generate_delta_usage(chunk.usage)

                # 生成结束
                if chunk.choices[0].finish_reason is not None:
                    content = "".join(content_chunks)
                    await self.on_generate_complete(content)
                    await self.on_generate_end()
                    await self.record_generate_usage(chunk.usage)

                    # 工具调用
                    if chunk.choices[0].finish_reason == "tool_calls":
                        keep_agent_loop = self.loop_flag_set_on_tool_calls(keep_agent_loop)

                        # 创建助手消息（包含工具调用）
                        _new_mem = await self.on_create_assistant_message(content, _tool_calls)

                        # 调用工具调用开始钩子
                        await self.on_tool_calls_start(_tool_calls)

                        # 执行工具调用
                        _tool_mem, _tool_func_task = await self._execute_tool_calls(
                            _tool_calls, tool_call_function,
                        )

                        await self.on_tool_calls_complete(_tool_mem, _tool_func_task)

                        # 更新运行时记忆
                        self._runtime_memories.append(_new_mem)
                        self._runtime_memories.extend(_tool_mem)
                    else:
                        # 创建助手消息（纯文本）
                        _new_mem = await self.on_create_assistant_message(content)

                        # 更新运行时记忆
                        self._runtime_memories.append(_new_mem)

                    # 调用循环结束方法
                    await self.on_iteration_end(iteration, memories + self._runtime_memories)

        # Agent 完成
        await self.on_agent_complete(memories + self._runtime_memories)

        return self._new_agent_memories_create, self._new_agent_messages_create

    # 生命周期方法 - 子类可以覆盖以自定义行为

    async def on_agent_start(self, memories: list[ChatCompletionMessageParam]) -> None:
        """Agent 开始执行前调用。"""

    # 循环控制方法 - 子类可以覆盖以自定义循环行为

    def loop_flag_init(self) -> Any:
        """初始化循环标志，返回循环控制值。"""
        if self.loop_control:
            return self.loop_control
        return True

    def loop_flag_unset_on_iter_start(self, current_value: Any, iteration: int) -> Any:
        """每次循环开始时调用，返回新的循环控制值。"""
        return False

    def loop_flag_set_on_tool_calls(self, current_value: Any) -> Any:
        """当需要工具调用时调用，返回新的循环控制值。"""
        return True

    def loop_flag_should_continue(self, current_value: Any) -> bool:
        """根据循环控制值判断是否继续循环。"""
        return bool(current_value)

    async def on_iteration_start(self, iteration: int) -> None:
        """每次循环开始前调用。"""

    async def on_iteration_end(self, iteration: int, memories: list[ChatCompletionMessageParam]) -> None:
        """每次循环结束时调用。"""

    async def prepare_kwargs(self, memories: list[ChatCompletionMessageParam]) -> dict:
        """准备 LLM 请求的 kwargs 参数。"""
        return {"stream_options": {"include_usage": True}}

    async def prepare_tools(self, memories: list[ChatCompletionMessageParam]) -> tuple[list[ChatCompletionToolParam], dict[str, ToolClosure]]:
        """准备 LLM 请求的工具列表和工具函数字典。"""
        return self.tools, self.tool_call_function
    async def on_generate_start(self) -> None:
        """开始生成内容时调用。"""

    async def on_generate_delta(self, delta: str) -> None:
        """接收到内容生成的每个 delta 时调用。"""

    async def on_generate_complete(self, content: str) -> None:
        """内容生成完成时调用。"""

    async def on_generate_end(self) -> None:
        """生成过程结束时调用。"""

    async def record_generate_delta_usage(self, usage: CompletionUsage) -> None:
        """记录内容生成 delta 使用的 API 调用花费。"""

    async def record_generate_usage(self, usage: CompletionUsage) -> None:
        """记录内容生成使用的 API 调用花费。"""

    async def on_create_assistant_message(self, content: str, tool_calls: list[ChoiceDeltaToolCall] | None = None) -> ChatCompletionAssistantMessageParam:
        """创建助手消息时调用。"""
        if tool_calls :
            tool_calls_as_dict = [
                tool_call.model_dump()
                for tool_call in tool_calls
            ]
            return ChatCompletionAssistantMessageParam(
                role="assistant",
                content=content,
                tool_calls=tool_calls_as_dict,
            )
        else:
            return ChatCompletionAssistantMessageParam(
                role="assistant",
                content=content,
            )


    async def on_tool_calls_start(self, tool_calls: list[ChoiceDeltaToolCall]) -> None:
        """工具调用开始前调用。"""

    async def on_tool_calls_start_batch(self, tool_calls: list[ChoiceDeltaToolCall], tool_func: dict[str, ToolClosure], tool_func_params: dict[str, dict]) -> None:
        """工具调用批次开始时调用。"""

    async def on_tool_call_start(self, tool_name: str, params: dict) -> None:
        """单个工具调用开始时调用。"""

    async def on_tool_call_complete(self, tool_name: str, result: ToolTaskResult) -> None:
        """单个工具调用完成时调用。"""

    async def on_tool_call_error(self, tool_name: str, error: Exception) -> None:
        """单个工具调用出错时调用。"""

    async def on_tool_calls_complete_batch(self, tool_responses: list[ChatCompletionToolMessageParam]) -> None:
        """工具调用响应处理完成时调用。"""

    async def on_tool_calls_complete(self,
                                     tool_mem: ChatCompletionToolMessageParam,
                                     tool_func_task: dict[str, Task[ToolTaskResult] | None]) -> None:
        """所有工具调用完成时调用。"""

    async def on_agent_complete(self, memories: list[ChatCompletionMessageParam]) -> None:
        """Agent 执行完成时调用。"""
