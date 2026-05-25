# api/agent/tools/sub_agent/utils.py

"""sub_agent 工具的辅助函数。"""

import secrets
import string


def generate_session_alias() -> str:
    """生成 6 位随机字母数字字符串作为会话别名。

    格式：[a-z0-9]{4}
    示例：a7x3, b2k9, z4m1

    Returns:
        6 位随机别名
    """
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(6))