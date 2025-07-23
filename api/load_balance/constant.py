from .load_balancer import LoadBalancer
from .service_instance import AsyncOpenAIServiceInstance
from .service_regeistry import ServiceConfig, ServiceRegistry

__all__ = [
    "DEEPSEEK_REASONER_SERVICE_NAME",
    "LOAD_BLANCER",
    "QWEN_3_235B_SERVICE_NAME",
    "QWEN_MAX_SERVICE_NAME",
    "QWEN_PLUS_SERVICE_NAME",
    "QWEN_VL_OCR_SERVICE_NAME",
    "QWEN_TEXTEMBEDDING_SERVICE_NAME"
]

LOAD_BLANCER = LoadBalancer(ServiceRegistry())

DEEPSEEK_REASONER_SERVICE_NAME = "deepseek"
QWEN_3_235B_SERVICE_NAME = "qwen3-235b-a22b"
QWEN_MAX_SERVICE_NAME = "qwen-max"
QWEN_PLUS_SERVICE_NAME = "qwen-plus"
QWEN_VL_OCR_SERVICE_NAME = "qwen-vl-ocr"
QWEN_TEXT_EMBEDDING_SERVICE_NAME = "qwen-text-embedding"