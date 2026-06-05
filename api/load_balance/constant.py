from api.load_balance.data_model import RetryConfigForAPIError
from .load_balancer import LoadBalancer
from .service_instance import AsyncOpenAIServiceInstance
from .service_regeistry import ServiceConfig, ServiceRegistry

__all__ = [
    "DEEPSEEK_V4_FLASH_SERVICE_NAME",
    "DEEPSEEK_V4_PRO_SERVICE_NAME",
    "GLM_5_SERVICE_NAME",
    "GLM_4_7_SERVICE_NAME",
    "LOAD_BLANCER",
    "QWEN_3_235B_SERVICE_NAME",
    "QWEN_MAX_SERVICE_NAME",
    "QWEN_PLUS_SERVICE_NAME",
    "QWEN_TEXT_EMBEDDING_SERVICE_NAME",
    "QWEN_VL_OCR_SERVICE_NAME"
]

LOAD_BLANCER = LoadBalancer(ServiceRegistry())

DEEPSEEK_V4_FLASH_SERVICE_NAME = "deepseek-v4-flash"
DEEPSEEK_V4_PRO_SERVICE_NAME = "deepseek-v4-pro"
GLM_5_SERVICE_NAME = "glm-5"
GLM_4_7_SERVICE_NAME = "glm-4.7"
QWEN_3_235B_SERVICE_NAME = "qwen3-235b-a22b"
QWEN_MAX_SERVICE_NAME = "qwen-max"
QWEN_PLUS_SERVICE_NAME = "qwen-plus"
QWEN_VL_OCR_SERVICE_NAME = "qwen-vl-ocr"
QWEN_TEXT_EMBEDDING_SERVICE_NAME = "qwen-text-embedding"

GLM_RETRY_CONFIG_FOR_APIERROR = RetryConfigForAPIError(
    error_code_to_match=["1302","1303","1305"]
)