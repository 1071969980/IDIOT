import os
import asyncio
from loguru import logger
from collections.abc import Iterable

import httpx
from openai.types.chat import ChatCompletionMessageParam, ChatCompletion

from .data_model import RetryConfig
from pydantic import BaseModel

import logfire


class RetryConfigForHTTPError(BaseModel):
    situations: dict[int, RetryConfig]


DEFAULT_RETRY_CONFIG = RetryConfigForHTTPError(
    situations={
        429: RetryConfig(max_retry=10, retry_interval_seconds=10),  # 限流错误
    },
)


async def farui_httpx_async_generate(
        messages: Iterable[ChatCompletionMessageParam] | list[dict]) -> tuple[str, int]:
    key = os.getenv("DASHSCOPE_API_KEY")
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    body = {
        "model": "farui-plus",
        "input": {
            "messages": messages,
        },
        "parameters": {
            "result_format": "message",
        },
    }
    retry_times = dict.fromkeys(DEFAULT_RETRY_CONFIG.situations.keys(), 0)

    while True:
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                response = await client.post(url, json=body, headers=headers)
                res_dict = response.json()
                content = res_dict["output"]["choices"][0]["message"]["content"]
                token_usage = res_dict["usage"]["total_tokens"]
                return content, token_usage
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code in DEFAULT_RETRY_CONFIG.situations.keys():
                retry_times[status_code] += 1
                retry_config = DEFAULT_RETRY_CONFIG.situations[status_code]
                if retry_times[status_code] >= retry_config.max_retry:
                    error_message = f"Too many retry. HTTP Error Code {status_code}. Response: {e}"
                    logfire.error(error_message)
                    return "", 0
                logfire.warning(f"Retrying... HTTP Error Code {status_code}. Response: {e}")
                await asyncio.sleep(retry_config.retry_interval_seconds)
                continue
            error_message = f"Unexpected HTTP Error Code {status_code}. Response: {e}"
            logfire.error(error_message)
            return "", 0
        except Exception as e:
            error_message = f"Unexpected error: {e}"
            logfire.error(error_message)
            return "", 0