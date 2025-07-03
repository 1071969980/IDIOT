import os
from functools import lru_cache

from openai import AsyncOpenAI

@lru_cache(maxsize=1)
def async_client() -> AsyncOpenAI:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    return AsyncOpenAI(
        api_key=key,
        base_url="https://api.deepseek.com",
    )