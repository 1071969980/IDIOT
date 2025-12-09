from asyncio import Event
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID


from openai.types.chat.chat_completion_message_param import (
    ChatCompletionMessageParam,
)
from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel, Field

from api.agent.base_agent import AgentBase
from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.dynamic_tool_DI.constructor import (
    construct_tool as construct_dynamic_tool,
)
from api.chat.streaming_processor import StreamingProcessor
from api.workflow.langfuse_prompt_template.main_agent_explicitily_assert import (
    get_concluding_guidebook_test,
    get_concluding_prompt,
    get_concluding_prompt,
    get_guidence_prompt,
    get_guidence_system_prompt,
    get_conversation_script_test,
)

from .main_agent import MainAgent
import logfire

class MainAgentExplicitlyAssert(MainAgent):
    def __init__(
        self,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
        streaming_processor: StreamingProcessor,
        cancel_event: Event,
        service_name: str,
        tools: list[ChatCompletionToolParam],
        tool_call_function: dict[
            str,
            Callable[..., Coroutine[Any, Any, ToolTaskResult]],
        ],
        status_concluding_prompt: str | None = None,
        loop_control: Any = None,
        **kwargs,
    ):
        super().__init__(
            user_id,
            session_id,
            session_task_id,
            streaming_processor,
            cancel_event,
            service_name,
            tools,
            tool_call_function,
            loop_control,
            **kwargs,
        )

        self.status_concluding_prompt = status_concluding_prompt

        self.temp_guidence_memory: ChatCompletionAssistantMessageParam | None = None

    async def on_agent_start(self, 
                             memories: list[ChatCompletionMessageParam]) -> None:
        with logfire.span("api/agent/strategy/main_agent_explicitily_assert.py::on_agent_start"):
            await self.__on_agent_start(memories)

    async def __on_agent_start(self, 
                             memories: list[ChatCompletionMessageParam]) -> None:
        await super().on_agent_start(memories)

        conclusion_res = {"result": ""}

        class ConcludingStatusParamDefine(BaseModel):
            conclusion: str = Field(..., description="conclusion of the status")

        async def conclusion_call_back(param: BaseModel):
            if not isinstance(param, ConcludingStatusParamDefine):
                raise ValueError("expected param as ConcludingStatusParamDefine")
            conclusion_res["result"] = param.conclusion

        concluding_tool_name = "concluding_status"

        concluding_tool_define, concluding_tool_closure = construct_dynamic_tool(
            concluding_tool_name,
            "concluding the status, conclusion will be used for later",
            ConcludingStatusParamDefine,
            conclusion_call_back,
        )

        # concluding the status
        concluding_agent = AgentBase(
            cancel_event=self.cancel_event,
            tools=[
                concluding_tool_define,
            ],
            tool_call_function={
                concluding_tool_name: concluding_tool_closure,
            },
        )
        history_mem = self._runtime_memories.copy()

        if self.status_concluding_prompt is None:
            self.status_concluding_prompt = get_concluding_prompt(
                get_concluding_guidebook_test(),
                concluding_tool_name,
            )

        # append status concluding prompt
        history_mem.append(
            ChatCompletionAssistantMessageParam(
                role="assistant",
                content=self.status_concluding_prompt,
            ),
        )
        # try to conclude the status
        concluding_try = 0
        while concluding_try < 3 and conclusion_res["result"] == "":
            await concluding_agent.run(history_mem, self.service_name)
            concluding_try += 1
        if conclusion_res["result"] == "":
            raise ValueError("concluding status failed")

        # guidence
        guidence_res = {"result": ""}

        class ProvideGuidelinesParamDefine(BaseModel):
            guidelines: str = Field(
                ..., description="guidelines in the first person perspective"
            )

        async def guidence_call_back(param: BaseModel):
            if not isinstance(param, ProvideGuidelinesParamDefine):
                raise ValueError("expected param as ProvideGuidelinesParamDefine")
            guidence_res["result"] = param.guidelines

        guidence_tool_name = "provide_guidelines"

        guidence_tool_define, guidence_tool_closure = construct_dynamic_tool(
            guidence_tool_name,
            "provide execution guidelines for the other AI agent`s the next steps in the conversation.",
            ProvideGuidelinesParamDefine,
            guidence_call_back,
        )

        guidence_agent = AgentBase(
            cancel_event=self.cancel_event,
            tools=[
                guidence_tool_define,
            ],
            tool_call_function={
                guidence_tool_name: guidence_tool_closure,
            },
        )

        # render guidence chat prompt with conclusion result
        guidence_system_prompt = get_guidence_system_prompt()

        guidence_prompt = get_guidence_prompt(
            get_conversation_script_test(),
            conclusion_res["result"],
            guidence_tool_name,
        )

        guidence_memory = [
            ChatCompletionSystemMessageParam(
                role="system",
                content=guidence_system_prompt,
            ),
            ChatCompletionUserMessageParam(
                role="user",
                content=guidence_prompt,
            ),
        ]

        # try to provide guidence
        guidence_try = 0
        while guidence_try < 3 and guidence_res["result"] == "":
            await guidence_agent.run(guidence_memory, self.service_name)
            guidence_try += 1
        if guidence_res["result"] == "":
            raise ValueError("guidence failed")

        self.temp_guidence_memory = ChatCompletionAssistantMessageParam(
            role="assistant",
            content=guidence_res["result"],
        )

        self._runtime_memories.append(self.temp_guidence_memory)
        self._new_memories.append(self.temp_guidence_memory)
