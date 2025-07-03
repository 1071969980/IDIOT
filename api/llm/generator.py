import asyncio
from collections.abc import Iterable
from typing import Any, Literal, Optional, overload
from api.load_balance.service_instance import AsyncOpenAIServiceInstance
from api.load_balance.exception import (
    RequestTimeoutError,
    LimitExceededError,
    ServiceError,
)

import logfire
import openai
from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from .data_model import RetryConfigForAPIError

DEFAULT_RETRY_CONFIG = RetryConfigForAPIError(
    error_code_to_match=["429", "limit_requests"]
)

@overload
async def openai_async_generate(client: AsyncOpenAI,
                          model: str,
                          messages: Iterable[ChatCompletionMessageParam],
                          stream: Literal[True],
                          retry_configs: RetryConfigForAPIError = DEFAULT_RETRY_CONFIG,
                          **kwarg: dict[str, Any]) -> AsyncStream[ChatCompletionChunk]:
    ...

@overload
async def openai_async_generate(client: AsyncOpenAI,
                          model: str,
                          messages: Iterable[ChatCompletionMessageParam],
                          retry_configs: RetryConfigForAPIError = DEFAULT_RETRY_CONFIG,
                          **kwarg: dict[str, Any]) -> ChatCompletion:
    ...

async def openai_async_generate(client: AsyncOpenAI,
                          model: str,
                          messages: Iterable[ChatCompletionMessageParam],
                          retry_configs: RetryConfigForAPIError = DEFAULT_RETRY_CONFIG,
                          **kwarg: dict[str, Any]) -> ChatCompletion:
    try:
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            **kwarg,
        )
    except openai.APIError as e:
        if e.code in retry_configs.error_code_to_match:
            logfire.warning(f"Retrying... OpenAI API Error Code {e.code}.OpenAI API Error: {e.message}")
            raise LimitExceededError from e
        
        logfire.error(f"Unexpected OpenAI API Error Code {e.code}.OpenAI API Error: {e.message}")
        raise
    except Exception:
        raise
