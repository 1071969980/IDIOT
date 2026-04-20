# api/agent/tools/sub_agent/utils.py

"""sub_agent 工具的辅助函数。"""

import secrets
import string

from .definition_loader import SubAgentDefinition


def generate_session_alias() -> str:
    """生成 4 位随机字母数字字符串作为会话别名。

    格式：[a-z0-9]{4}
    示例：a7x3, b2k9, z4m1

    Returns:
        4 位随机别名
    """
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(4))


def format_tool_description(definitions: dict[str, SubAgentDefinition]) -> str:
    """格式化 sub_agent 工具的描述。

    动态生成包含可用 agent 列表的描述。

    Args:
        definitions: 可用的 agent 定义字典

    Returns:
        格式化的工具描述
    """
    agent_list = "\n".join([
        f"- {name}: {defn.description}"
        for name, defn in definitions.items()
    ])

    return f"""创建一个子 agent 会话来执行独立任务。

可用的系统内置子 agent：
{agent_list}

参数说明：
- agent_name: 要执行的子 agent 名称（从"可用的子 agent"列表选择）
- task: 给子 agent 的任务安排文本
- session_alias: （可选）要复用的会话别名

子 agent 的执行结果将作为此工具的返回值。"""
