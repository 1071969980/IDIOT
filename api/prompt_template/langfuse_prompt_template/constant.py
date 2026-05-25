from langfuse import get_client
from langfuse.model import TextPromptClient

from api.core.env_config import llm_service_config

# 配置验证由 LLMServiceConfig 处理，缺少必填字段会抛出 ValidationError
LANGFUSE_SECRET_KEY = llm_service_config.langfuse_secret_key.get_secret_value()
LANGFUSE_PUBLIC_KEY = llm_service_config.langfuse_public_key.get_secret_value()
LANGFUSE_HOST = llm_service_config.langfuse_host

LANGFUSE_CLIENT = get_client()

def get_prompt_from_langfuse(
        prompt_path: str,
        production: bool = True,
        label: str | None = None,
        version: int | None = None,
) -> TextPromptClient | None:
    try:
        if production:
            prompt = LANGFUSE_CLIENT.get_prompt(
                prompt_path,
            )
        elif label:
            prompt = LANGFUSE_CLIENT.get_prompt(
                prompt_path,
                label=label,
            )
        elif version:
            prompt = LANGFUSE_CLIENT.get_prompt(
                prompt_path,
                version=version,
            )
        return prompt
    
    except Exception:
        return None

# use TextPromptClient.complie(**kwargs) to get rendered prompt
# use TextPromptClient.prompt to access plain text prompt
