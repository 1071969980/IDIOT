import asyncio
from abc import ABC
from asyncio import Event, Task
from typing import Any, TypedDict
from uuid import UUID, uuid4

import logfire
import ujson
from openai.types.chat import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_assistant_message_param import ChatCompletionAssistantMessageParam
from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaToolCall,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_message_tool_call import Function
from openai.types.chat.chat_completion_tool_message_param import ChatCompletionToolMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.completion_usage import CompletionUsage

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.chat.exception import SessionChatTaskCancelled
from api.chat.sql_stat.u2a_agent_msg.utils import _U2AAgentMessageCreate
from api.chat.sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryCreate,
)
from api.llm.generator import DEFAULT_RETRY_CONFIG
from api.load_balance import LOAD_BLANCER
from api.load_balance.delegate.openai import generation_delegate_for_async_openai
from api.logger.datamodel import LangFuseSpanAttributes
from api.logger.time import now, now_iso


class AgentRuntimeToolCallData(TypedDict):
    openai_tool_call_id: str
    name: str
    param: dict
    function: ToolClosure | None
    task: Task[ToolTaskResult] | None

class AgentBase(ABC):
    """Agent 基类，提供核心 agent 循环功能和生命周期方法。"""

    def __init__(
        self,
        cancel_event: Event,
        tools: list[ChatCompletionToolParam],
        tool_call_function: dict[str, ToolClosure],
        loop_control: Any = None,
    ):
        self.cancel_event = cancel_event
        self.tools = tools
        self.tool_call_function = tool_call_function
        self.loop_control = loop_control

        # 内部状态
        self._runtime_memories: list[ChatCompletionMessageParam] = []
        self._new_memories: list[ChatCompletionAssistantMessageParam | ChatCompletionToolMessageParam] = []
        self._new_agent_memories_create: list[_AgentShortTermMemoryCreate] = []
        self._new_agent_messages_create: list[_U2AAgentMessageCreate] = []
        self._new_agent_msg_sub_seq_index_counter = 0

    def _parse_tool_calls_robust(self, tool_call_deltas: list[ChoiceDeltaToolCall]) -> list[ChatCompletionMessageToolCall]:
        """
        健壮版本的解析函数，返回 ChatCompletionMessageToolCall 列表

        Args:
            tool_call_deltas: ChoiceDeltaToolCall 列表

        Returns:
            ChatCompletionMessageToolCall 对象列表
        """

        if not tool_call_deltas:
            return []

        tool_calls_by_index = {}

        for delta in tool_call_deltas:
            try:
                index = delta.index
                function_delta = delta.function

                if function_delta is None:
                    continue

                if index not in tool_calls_by_index:
                    tool_calls_by_index[index] = {
                        'name': '',
                        'arguments': '',
                        'id': delta.id or f"tool_call_{index}"
                    }

                # 安全地累加字符串
                if function_delta.name is not None:
                    tool_calls_by_index[index]['name'] += function_delta.name

                if function_delta.arguments is not None:
                    tool_calls_by_index[index]['arguments'] += function_delta.arguments

            except (AttributeError, KeyError) as e:
                print(f"Warning: Failed to parse tool call delta: {e}")
                continue

        # 按 index 排序构建 ChatCompletionMessageToolCall 对象
        tool_calls = []

        for index in sorted(tool_calls_by_index.keys()):
            tool_call_data = tool_calls_by_index[index]

            # 构建 Function 对象
            function = Function(
                name=tool_call_data["name"],
                arguments=tool_call_data["arguments"],
            )

            # 构建 ChatCompletionMessageToolCall 对象
            tool_call = ChatCompletionMessageToolCall(
                id=tool_call_data["id"],
                function=function,
                type="function",
            )

            tool_calls.append(tool_call)

        return tool_calls

    async def _execute_tool_calls(
        self,
        tool_calls: list[ChatCompletionMessageToolCall],
        tool_call_function: dict[str, ToolClosure],
    ) -> tuple[list[ChatCompletionToolMessageParam], dict[UUID, AgentRuntimeToolCallData]]:
        """执行工具调用并返回工具消息参数。"""



        # 提取工具函数和参数
        tool_exec_data = {
            uuid4() : AgentRuntimeToolCallData(
                openai_tool_call_id=tool_call.id,
                name = tool_call.function.name, # type: ignore
                param = ujson.loads(tool_call.function.arguments) if tool_call.function.arguments else {}, # type: ignore
                function = tool_call_function.get(tool_call.function.name), # type: ignore
                task = None
            )
            for tool_call in tool_calls
        }


        # 通知工具调用开始
        await self.on_tool_calls_start_batch(tool_exec_data)

        for uuid, tool_call_data in tool_exec_data.items():
            if tool_call_data["function"]:
                # 通知单个工具调用开始
                await self.on_tool_call_start(
                    tool_call_data["name"],
                    tool_call_data["param"],
                )

                # 使用 asyncio.create_task 创建异步任务
                tool_call_data["task"] = asyncio.create_task(
                    tool_call_data["function"](
                        **tool_call_data["param"],
                        exec_uuid=uuid,
                    ),
                )

        # 执行所有工具调用
        all_task = [data["task"] for data in tool_exec_data.values()]
        done, pending = await asyncio.wait(
            [task for task in all_task if task is not None],
            return_when=asyncio.ALL_COMPLETED,
        )

        await self.on_tool_calls_complete_batch(tool_exec_data)

        # 收集结果并处理每个工具调用的结果

        tool_result: dict[UUID, str] = {}
        for tool_call_uuid, tool_call_data in tool_exec_data.items():
            if tool_call_data["task"] is None:
                result = f"{tool_call_data['name']} Response : \n{tool_call_data['name']} can not be called right now"
                tool_result[tool_call_uuid] = result
                await self.on_tool_call_error(tool_call_data["name"], ValueError("Tool function not found"))
            elif hasattr(tool_call_data["task"], "exception") and (e := tool_call_data["task"].exception()):
                result = f"{tool_call_data['name']} Response : \n{tool_call_data['name']} raised exception : {e!s}"
                tool_result[tool_call_uuid] = result
                await self.on_tool_call_error(tool_call_data["name"], e)
            else:
                tool_result[tool_call_uuid] = f"{tool_call_data['name']} Response : \n{tool_call_data['task'].result().str_content}"
                await self.on_tool_call_complete(tool_call_data["name"], tool_call_data["task"].result())

        # 创建工具消息参数
        tool_mems = [
            ChatCompletionToolMessageParam(
                content=tool_result[uuid],
                role="tool",
                tool_call_id=tool_exec_data[uuid]["openai_tool_call_id"],
            )
            for uuid in tool_exec_data.keys()
        ]

        return tool_mems, tool_exec_data

    async def run(self, memories: list[ChatCompletionMessageParam], service_name: str) -> tuple[list[_AgentShortTermMemoryCreate], list[_U2AAgentMessageCreate]]:
        """执行 agent 循环。"""
        langfuse_observation_attributes = LangFuseSpanAttributes(
            observation_type="span",
        ) # type: ignore
        with logfire.span("api/agent/base_agent.py::run",
                          **langfuse_observation_attributes.model_dump(mode="json", by_alias=True)) as span:
            return await self.__run(memories, service_name)

    async def __run(self, memories: list[ChatCompletionMessageParam], service_name: str) -> tuple[list[_AgentShortTermMemoryCreate], list[_U2AAgentMessageCreate]]:
        """执行 agent 循环。"""
        # 初始化运行时记忆，将历史记忆作为运行时记忆的起始状态
        self._runtime_memories = memories.copy()
        self._new_memories = []  # 重置本次运行产生的新记忆

        # Agent 开始
        await self.on_agent_start(memories)

        # agent 循环
        keep_agent_loop = self.loop_flag_init()
        iteration = 0


        # 准备 LLM 请求参数
        kwargs = await self.prepare_kwargs(self._runtime_memories)

        # 准备工具
        tools, tool_call_function = await self.prepare_tools(self._runtime_memories)

        # 如果有工具，添加到 kwargs 中
        if tools:
            kwargs["tools"] = tools

        async def delegate(instance):
            return await generation_delegate_for_async_openai(
                instance,
                self._runtime_memories,
                DEFAULT_RETRY_CONFIG,
                stream=True,
                **kwargs,
            )

        langfuse_observation_attributes = LangFuseSpanAttributes(
            observation_type="generation",
            input=ujson.dumps(self._runtime_memories),
            model_name=service_name,
            model_parameters=ujson.dumps(kwargs),
            completion_start_time=now_iso(),
        ) # type: ignore
        
        with logfire.span("api/agent/base_agent.py::__run#gen_loop",
                          **langfuse_observation_attributes.model_dump(mode="json", by_alias=True)) as gen_loop_span:
            # gen_loop
            while self.loop_flag_should_continue(keep_agent_loop):
                iteration += 1
                keep_agent_loop = self.loop_flag_unset_on_iter_start(keep_agent_loop, iteration)

                # 循环开始
                await self.on_iteration_start(iteration)

                result = await LOAD_BLANCER.execute(service_name, delegate)

                content_chunks = []
                reasoning_content_chunks = []

                _tool_calls_delta: list[ChoiceDeltaToolCall] = []

                # 开始生成内容
                await self.on_generate_start()

                # 处理流式响应
                async for chunk in result:
                    # ====== cancel handle ======
                    if self.cancel_event.is_set():
                        # record message until cancel
                        interrupt_suffix = "\n(INTERRUPTED BY USER)"
                        content="".join(content_chunks) + interrupt_suffix
                        reasoning_content = "".join(reasoning_content_chunks)
                        await self.on_generate_delta(interrupt_suffix)
                        await self.on_generate_complete(content)
                        _new_mem = await self.on_create_assistant_memory(content, reasoning_content)
                        self._runtime_memories.append(_new_mem)
                        self._new_memories.append(_new_mem)
                        await self.on_iteration_end(iteration, self._runtime_memories)
                        await self.on_agent_complete()
                        await self.on_agent_cancel()
                        raise SessionChatTaskCancelled(new_agent_memory=self._new_agent_memories_create,
                                                    new_agent_message=self._new_agent_messages_create)
                    # ====== cancel handle ======

                    if chunk.choices[0].delta.tool_calls:
                        _tool_calls_delta += chunk.choices[0].delta.tool_calls
                    if chunk.choices[0].delta.content:
                        content_chunks.append(chunk.choices[0].delta.content)
                        await self.on_generate_delta(chunk.choices[0].delta.content)
                        await self.record_generate_delta_usage(chunk.usage)
                    if chunk.choices[0].delta.model_extra and chunk.choices[0].delta.model_extra.get("reasoning_content"):
                        reasoning_content_chunk = chunk.choices[0].delta.model_extra.get("reasoning_content", "")
                        await self.on_generate_delta(reasoning_content_chunk)
                        await self.record_generate_delta_usage(chunk.usage)
                        reasoning_content_chunks.append(reasoning_content_chunk)

                    # 生成结束
                    if chunk.choices[0].finish_reason is not None:
                        content = "".join(content_chunks)
                        reasoning_content = "".join(reasoning_content_chunks)
                        await self.on_generate_complete(content)
                        await self.record_generate_usage(chunk.usage)

                        # 工具调用
                        if chunk.choices[0].finish_reason == "tool_calls":
                            keep_agent_loop = self.loop_flag_set_on_tool_calls(keep_agent_loop)

                            _tool_calls = self._parse_tool_calls_robust(_tool_calls_delta)

                            # 创建助手消息（包含工具调用）
                            _new_mem = await self.on_create_assistant_memory(content, reasoning_content, _tool_calls)

                            # 执行工具调用
                            _tool_mem, _tool_func_task = await self._execute_tool_calls(
                                _tool_calls, tool_call_function,
                            )

                            # 更新运行时记忆
                            self._runtime_memories.append(_new_mem)
                            self._runtime_memories.extend(_tool_mem)
                            self._new_memories.append(_new_mem)
                            self._new_memories.extend(_tool_mem)
                        else:
                            # 创建助手消息（纯文本）
                            _new_mem = await self.on_create_assistant_memory(content, reasoning_content)

                            # 更新运行时记忆
                            self._runtime_memories.append(_new_mem)
                            self._new_memories.append(_new_mem)

                # 调用循环结束方法
                await self.on_iteration_end(iteration, self._runtime_memories)
            
            langfuse_observation_attributes_output = LangFuseSpanAttributes(
                output=ujson.dumps(self._new_memories),
            ) # type: ignore
            gen_loop_span.set_attributes(langfuse_observation_attributes_output.model_dump(mode="json", by_alias=True))

        # Agent 完成
        await self.on_agent_complete()

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

    async def record_generate_delta_usage(self, usage: CompletionUsage) -> None:
        """记录内容生成 delta 使用的 API 调用花费。"""

    async def record_generate_usage(self, usage: CompletionUsage) -> None:
        """记录内容生成使用的 API 调用花费。"""

    async def on_create_assistant_memory(self, content: str, reasoning_content: str, tool_calls: list[ChatCompletionMessageToolCall] | None = None) -> ChatCompletionAssistantMessageParam:
        """创建助手消息时调用。"""
        if tool_calls :
            tool_calls_as_dict = [
                tool_call.model_dump()
                for tool_call in tool_calls
            ]
            return ChatCompletionAssistantMessageParam(
                role="assistant",
                content=content,
                reasoning_content=reasoning_content,
                tool_calls=tool_calls_as_dict,
            ) # type: ignore
        else:
            return ChatCompletionAssistantMessageParam(
                role="assistant",
                content=content,
                reasoning_content=reasoning_content,
            ) # type: ignore

    async def on_tool_calls_start_batch(self, tool_exec_data: dict[UUID, AgentRuntimeToolCallData]) -> None:
        """工具调用批次开始时调用。"""

    async def on_tool_calls_complete_batch(self, tool_exec_data: dict[UUID, AgentRuntimeToolCallData]) -> None:
        """工具调用响应处理完成时调用。"""

    async def on_tool_call_start(self, tool_name: str, params: dict) -> None:
        """单个工具调用开始时调用。"""

    async def on_tool_call_complete(self, tool_name: str, result: ToolTaskResult) -> None:
        """单个工具调用完成时调用。"""

    async def on_tool_call_error(self, tool_name: str, error: BaseException) -> None:
        """单个工具调用出错时调用。"""

    async def on_agent_complete(self) -> None:
        """Agent 执行完成时调用。"""
        for mem in self._new_memories:
            if mem.get("reasoning_content"):
                mem["reasoning_content"] = None # type: ignore

    async def on_agent_cancel(self) -> None:
        """Agent 被取消时调用。"""