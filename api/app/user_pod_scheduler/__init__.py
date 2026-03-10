"""用户 Pod 调度器路由模块"""

from . import endpoints
from .router_declare import router

__all__ = ["router", "endpoints"]