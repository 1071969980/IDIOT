from collections.abc import Iterable
from typing import Any, Literal, overload

from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from api.llm.data_model import RetryConfigForAPIError
from api.llm.generator import openai_async_generate
from api.load_balance.service_instance import (
    AsyncOpenAIServiceInstance,
    ServiceInstanceBase,
)


@overload
async def generation_delegate_for_async_openai(
        service_instance: AsyncOpenAIServiceInstance,
        messages: Iterable[ChatCompletionMessageParam],
        stream: Literal[True],
        retry_configs: RetryConfigForAPIError,
        **kwarg: dict[str, Any],
) -> AsyncStream[ChatCompletionChunk]:
    ...

@overload
async def generation_delegate_for_async_openai(
        service_instance: AsyncOpenAIServiceInstance,
        messages: Iterable[ChatCompletionMessageParam],
        retry_configs: RetryConfigForAPIError,
        **kwarg: dict[str, Any],
) -> ChatCompletion:
    ...

async def generation_delegate_for_async_openai(
        service_instance: AsyncOpenAIServiceInstance,
        messages: Iterable[ChatCompletionMessageParam],
        retry_configs: RetryConfigForAPIError,
        **kwarg: dict[str, Any],
) -> ChatCompletion:
    assert isinstance(service_instance, ServiceInstanceBase)

    return await openai_async_generate(
        client=service_instance.client,
        model=service_instance.model,
        messages=messages,
        retry_configs=retry_configs,
        **kwarg,
    )
