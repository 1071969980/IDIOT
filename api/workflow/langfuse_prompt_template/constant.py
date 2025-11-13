import os
from langfuse import get_client

LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST")

if not (LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY and LANGFUSE_HOST):
    raise Exception("env vars LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_HOST are required")

LANGFUSE_CLIENT = get_client()

def _get_prompt_from_langfuse(
        prompt_path: str,
        production: bool = True,
        label: str | None = None,
        version: int | None = None
):
    try:
        if production:
            prompt = LANGFUSE_CLIENT.get_prompt(
                prompt_path
            )
        elif label:
            prompt = LANGFUSE_CLIENT.get_prompt(
                prompt_path,
                label=label
            )
        elif version:
            prompt = LANGFUSE_CLIENT.get_prompt(
                prompt_path,
                version=version
            )
        return prompt
    
    except Exception as e:
        return None