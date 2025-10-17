from collections.abc import Iterable
from typing import Any, Literal, overload

from openai import NOT_GIVEN, AsyncOpenAI, AsyncStream, NotGiven
from openai.types import CreateEmbeddingResponse
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from api.llm.data_model import RetryConfigForAPIError
from api.llm.generator import openai_async_generate, openai_async_embedding
from api.load_balance.service_instance import (
    AsyncOpenAIServiceInstance,
    ServiceInstanceBase,
)


@overload
async def generation_delegate_for_async_openai(
        service_instance: AsyncOpenAIServiceInstance,
        messages: Iterable[ChatCompletionMessageParam],
        retry_configs: RetryConfigForAPIError,
        /,
        stream: Literal[True],
        **kwargs: dict[str, Any],
) -> AsyncStream[ChatCompletionChunk]:
    ...

@overload
async def generation_delegate_for_async_openai(
        service_instance: AsyncOpenAIServiceInstance,
        messages: Iterable[ChatCompletionMessageParam],
        retry_configs: RetryConfigForAPIError,
        /,
        **kwargs: dict[str, Any],
) -> ChatCompletion:
    ...

async def generation_delegate_for_async_openai(
        service_instance: AsyncOpenAIServiceInstance,
        messages: Iterable[ChatCompletionMessageParam],
        retry_configs: RetryConfigForAPIError,
        /,
        **kwargs: dict[str, Any],
) -> ChatCompletion:
    assert isinstance(service_instance, AsyncOpenAIServiceInstance)

    return await openai_async_generate(
        client=service_instance.client,
        model=service_instance.model,
        messages=messages,
        retry_configs=retry_configs,
        **kwargs,
    )

async def embedding_delegate_for_async_openai(
    service_instance: ServiceInstanceBase,
    text: str | list[str],
    dimensions: int | NotGiven = NOT_GIVEN,
    encoding_format: str = "float",
) -> CreateEmbeddingResponse:
    assert isinstance(service_instance, AsyncOpenAIServiceInstance)

    return await openai_async_embedding(
        client=service_instance.client,
        text=text,
        model=service_instance.model,
        dimensions=dimensions,
        encoding_format=encoding_format,
    )