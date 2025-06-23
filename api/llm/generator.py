import asyncio
from collections.abc import Iterable
from typing import Any

import openai
from loguru import logger
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from .data_model import RetryConfig, RetryConfigForAPIError

DEFAULT_RETRY_CONFIG = RetryConfigForAPIError(
    situations={
        "429": RetryConfig(max_retry=10, retry_interval_seconds=10),
    },
)
async def openai_async_generate(client: AsyncOpenAI,
                          model: str,
                          messages: Iterable[ChatCompletionMessageParam],
                          retry_configs: RetryConfigForAPIError = DEFAULT_RETRY_CONFIG,
                          **kwarg: dict[str, Any]) -> ChatCompletion | None:
    retry_times = dict.fromkeys(retry_configs.situations.keys(), 0)

    while True:
        try:
            return await client.chat.completions.create(
                model=model,
                messages=messages,
                **kwarg,
            )
        except openai.APIError as e:
            if e.code in retry_configs.situations.keys():
                retry_times[e.code] += 1
                retry_config = retry_configs.situations[e.code]
                if retry_times[e.code] >= retry_config.max_retry:
                    error_message = f"Too many retry. OpenAI API Error Code {e.code}.OpenAI API Error: {e.message}"
                    logger.error(error_message)
                    return None
                logger.warning(f"Retrying... OpenAI API Error Code {e.code}.OpenAI API Error: {e.message}")
                await asyncio.sleep(retry_config.retry_interval_seconds)
                continue
            error_message = f"OpenAI API Error Code {e.code}.OpenAI API Error Body: {e.body}"
            logger.error(error_message)
            return None
        except Exception as e:
            error_message = f"Unexpect OpenAI API Error: {e}"
            logger.error(error_message)
            return None
