"""用户文件系统 API 端点入口

此模块作为入口点，导入各个功能模块以注册路由到 router。
所有端点都使用同一个 router 实例（从 router_declare.py 导入）。
"""

# 导入各个功能模块以注册路由
from . import directory_ops  # noqa: F401
from . import file_ops  # noqa: F401
from . import manage_ops  # noqa: F401
from . import project  # noqa: F401
from . import query_ops  # noqa: F401

# 导出 router 供外部使用
from .router_declare import router

__all__ = ["router"]