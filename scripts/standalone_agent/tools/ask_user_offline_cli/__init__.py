"""ask_user_offline_cli 工具包

离线版的 ask_user 工具，使用 input() 替代 HIL 组件实现命令行用户交互。
"""

from .constructor import construct_ask_user_offline_cli

__all__ = ["construct_ask_user_offline_cli"]
