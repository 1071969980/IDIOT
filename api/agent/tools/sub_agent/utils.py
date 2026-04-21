# api/agent/tools/sub_agent/utils.py

"""sub_agent 工具的辅助函数。"""

import secrets
import string

from .definition_loader import SubAgentDefinition


def generate_session_alias() -> str:
    """生成 6 位随机字母数字字符串作为会话别名。

    格式：[a-z0-9]{4}
    示例：a7x3, b2k9, z4m1

    Returns:
        6 位随机别名
    """
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(6))


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

    return f"""创建一个子代理来执行任务。

内置的系统子代理：
{agent_list}

参数说明：
- agent_name: 要执行的子代理名称
- task: 给子代理的任务描述文本
- context_mode: 上下文模式，"standalone"（独立上下文）或 "fork"（继承当前上下文），为空时使用子代理定义文件中指定的默认值
- should_feedback: 是否要求子代理使用 feed_message 工具向你反馈，为空时使用子代理定义文件中指定的默认值"""