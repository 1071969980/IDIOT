import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.absolute()))

import asyncio

from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

# from api.llm import openai_async_generate
# from api.llm.qwen import async_client as qwen_async_client

from api.llm import farui_httpx_async_generate


def main():
    sys_prompt = ChatCompletionSystemMessageParam(
        role="system",
        content="You are a helpful assistant.",
    )
    user_prompt = ChatCompletionUserMessageParam(
        role="user",
        content="请告诉我合同签署的流程中的注意事项",
    )

    completion = asyncio.run(
        farui_httpx_async_generate(
            messages=[sys_prompt, user_prompt],
        ),
    )
    
    print(completion)

if __name__ == "__main__":
    import dotenv
    root_path = Path(__file__).parent.parent.parent.absolute()
    dotenv.load_dotenv(root_path / "docker" /".env")
    main()
