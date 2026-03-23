from functools import lru_cache

from openai import AsyncOpenAI

from api.core.env_config import llm_service_config

@lru_cache(maxsize=1)
def async_client() -> AsyncOpenAI:
    key = llm_service_config.dashscope_api_key.get_secret_value()
    return AsyncOpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )