from langfuse import get_client
from langfuse.model import TextPromptClient

# langfuse 配置由 get_client() 自行从 LANGFUSE_* 环境变量读取；
# 缺失时返回禁用 client（仅警告，不崩），其 get_prompt() 抛异常由下方 try-except 兜底返回 None。
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
