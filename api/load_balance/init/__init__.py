from .deepseek_service import register_deepseek_reasoner_service
from .qwen_commercial_service import register_qwen_max_service, register_qwen_plus_service

# dont export any symbols
__all__ = []

register_deepseek_reasoner_service()
register_qwen_max_service()
register_qwen_plus_service()