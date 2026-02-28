"""
MCP 连接测试命令
"""

from .command import TestMcpConnectionCommand as Command
from .data_model import (
    TestMcpConnectionInput as Input,
    TestMcpConnectionOutput as Output,
)