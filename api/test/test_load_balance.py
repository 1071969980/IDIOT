import sys
import os
# config os env in debug console

from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.absolute()))

import asyncio

from api.load_balance import LOAD_BLANCER, DEEPSEEK_REASONER_SERVICE_NAME
from api.load_balance.delegate.openai import generation_delegate_for_async_openai
from api.llm.generator import DEFAULT_RETRY_CONFIG


def test_load_balance():
    async def run_test():
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "请告诉我合同签署的流程中的注意事项"},
        ]

        def delegate(service_instance):
            return generation_delegate_for_async_openai(
                service_instance,
                messages,
                DEFAULT_RETRY_CONFIG
            )

        result = await LOAD_BLANCER.execute(
            DEEPSEEK_REASONER_SERVICE_NAME,
            delegate
        )
        print("Test result:", result)
    
    asyncio.run(run_test())

if __name__ == "__main__":
    test_load_balance()