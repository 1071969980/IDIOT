# api/agent/tools/sub_agent/__init__.py

"""sub_agent 工具模块。

该工具允许主 agent 创建隔离的子 agent 会话，支持：
- 独立的上下文和工具配置
- 会话复用（通过别名）
- 从用户空间定义文件加载 agent 配置
"""

from .config_data_model import (
    DEFAULT_TOOL_CONFIG,
    GENERATION_TOOL_PARAM,
    SubAgentToolConfig,
    SubAgentToolScope,
    SubAgentParamDefine,
    TOOL_NAME,
)
__all__ = [
    "DEFAULT_TOOL_CONFIG",
    "GENERATION_TOOL_PARAM",
    "SubAgentToolConfig",
    "SubAgentToolScope",
    "SubAgentParamDefine",
    "TOOL_NAME",
]
