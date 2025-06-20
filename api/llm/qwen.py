import os
from functools import lru_cache

from openai import AsyncOpenAI

@lru_cache(maxsize=1)
def async_client() -> AsyncOpenAI:
    key = os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )