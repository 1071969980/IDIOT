from api.llm.zhipu import async_client as zhipu_async_client

from ..constant import (
    GLM_5_SERVICE_NAME,
    GLM_4_7_SERVICE_NAME,
    LOAD_BLANCER,
)
from ..service_instance import AsyncOpenAIServiceInstance, ZhipuGLMServiceInstance


def register_glm_5_service() -> None:
    service_reg = LOAD_BLANCER.registry
    zhipu_instance = ZhipuGLMServiceInstance(
        name="zhipu",
        openai_client=zhipu_async_client(),
        model="glm-5",
    )
    service_reg.register_service(GLM_5_SERVICE_NAME, zhipu_instance)


def register_glm_4_7_service() -> None:
    service_reg = LOAD_BLANCER.registry
    zhipu_instance = AsyncOpenAIServiceInstance(
        name="zhipu",
        openai_client=zhipu_async_client(),
        model="glm-4.7",
    )
    service_reg.register_service(GLM_4_7_SERVICE_NAME, zhipu_instance)
