"""
Serialize ChatCompletionMessageParam to Markdown format.

将 ChatCompletionMessageParam 序列化为 Markdown 格式，支持完整的消息字段
包括 reasoning_content 和 tool_calls。
"""
import ujson
from pathlib import Path
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

# 与 message_parser 保持一致的分隔符
MESSAGE_SEPARATOR = "--#&%--"


def serialize_message(message: ChatCompletionMessageParam) -> str:
    """将单个消息序列化为 Markdown 格式

    Args:
        message: ChatCompletionMessageParam 对象

    Returns:
        Markdown 格式的字符串
    """
    lines = ["", MESSAGE_SEPARATOR, f"type: {message['role']}"]

    # reasoning_content 字段（仅 assistant 消息）
    if message.get("reasoning_content"):
        lines.append("reasoning_content: |")
        rc = message["reasoning_content"]
        if isinstance(rc, str):
            lines.append("  " + rc.replace("\n", "\n  "))

    # content 字段（所有消息类型都有）
    if message.get("content"):
        lines.append("content: |")
        content = message["content"]
        if isinstance(content, str):
            lines.append("  " + content.replace("\n", "\n  "))

    # tool_calls 字段（仅 assistant 消息）
    if message.get("tool_calls"):
        lines.append("tool_calls: |")
        # 使用 JSON 字符串格式
        tool_calls_json = ujson.dumps(message["tool_calls"], ensure_ascii=False)
        lines.append("  " + tool_calls_json.replace("\n", "\n  "))

    # tool_call_id 字段（仅 tool 消息）
    if message.get("tool_call_id"):
        lines.append(f"tool_call_id: {message['tool_call_id']}")

    lines.append(MESSAGE_SEPARATOR)
    return "\n".join(lines)


def serialize_messages(messages: list[ChatCompletionMessageParam]) -> str:
    """将多个消息序列化为 Markdown 格式

    Args:
        messages: ChatCompletionMessageParam 列表

    Returns:
        Markdown 格式的字符串
    """
    return "\n".join(serialize_message(msg) for msg in messages)


def save_messages(messages: list[ChatCompletionMessageParam], filepath: str) -> None:
    """将消息保存到 Markdown 文件

    Args:
        messages: ChatCompletionMessageParam 列表
        filepath: 输出文件路径
    """
    Path(filepath).write_text(serialize_messages(messages), encoding="utf-8")
