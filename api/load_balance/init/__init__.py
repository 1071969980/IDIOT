from .deepseek_service import (register_deepseek_v4_pro_service,
                               register_deepseek_v4_flash_service)
from .qwen_commercial_service import (register_qwen_3_235b_service,
                                      register_qwen_max_service,
                                      register_qwen_plus_service,
                                      register_qwen_vl_ocr_service,
                                      register_qwen_text_embedding_service)
from .zhipu_service import (register_glm_5_service,
                            register_glm_4_7_service)

# dont export any symbols
__all__ = []

def register_all_services() -> None:
    """注册所有 LLM 服务到负载均衡器（应在应用启动 lifespan 中调用，而非 import 时）。

    注册时会创建 LLM client 并访问必填环境变量（DEEPSEEK_API_KEY / ZHIPU_API_KEY 等），
    故必须延迟到启动阶段执行，避免 import 阶段因缺少 key 而崩溃。
    """
    register_deepseek_v4_pro_service()
    register_deepseek_v4_flash_service()
    register_glm_5_service()
    register_glm_4_7_service()
    # register_qwen_3_235b_service()
    # register_qwen_max_service()
    # register_qwen_plus_service()
    # register_qwen_vl_ocr_service()
    # register_qwen_text_embedding_service()