"""
Parse Markdown messages to ChatCompletionMessageParam format.
"""
import re
from pathlib import Path
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_system_message_param import ChatCompletionSystemMessageParam
from openai.types.chat.chat_completion_user_message_param import ChatCompletionUserMessageParam
from openai.types.chat.chat_completion_assistant_message_param import ChatCompletionAssistantMessageParam
from openai.types.chat.chat_completion_tool_message_param import ChatCompletionToolMessageParam

# 消息分隔符（与 MockStreamingProcessor 保持一致）
MESSAGE_SEPARATOR = "--#&%--"


def parse_markdown_messages(
    filepath: str,
) -> list[ChatCompletionMessageParam]:
    """解析 Markdown 文件为消息列表

    Args:
        filepath: Markdown 文件路径

    Returns:
        消息列表
    """
    content = Path(filepath).read_text(encoding="utf-8")

    # 使用独特的分隔符分割消息块
    pattern = rf'^{re.escape(MESSAGE_SEPARATOR)}$(.*?)(?=^{re.escape(MESSAGE_SEPARATOR)}$|^\Z)'
    blocks = re.findall(pattern, content, re.MULTILINE | re.DOTALL)

    messages = []
    for block in blocks:
        # 解析消息类型和内容
        type_match = re.search(r'^type:\s*(\w+)', block, re.MULTILINE)
        content_match = re.search(
            r'^content:\s*\|(.*?)(?=^\S|\Z)', block, re.MULTILINE | re.DOTALL
        )

        if not type_match:
            continue

        msg_type = type_match.group(1)
        msg_content = content_match.group(1).strip() if content_match else ""

        if msg_type == "system":
            messages.append(
                ChatCompletionSystemMessageParam(role="system", content=msg_content)
            )
        elif msg_type == "user":
            messages.append(
                ChatCompletionUserMessageParam(role="user", content=msg_content)
            )
        elif msg_type == "assistant":
            messages.append(
                ChatCompletionAssistantMessageParam(
                    role="assistant", content=msg_content
                )
            )
        elif msg_type == "tool":
            tool_name = re.search(r'^tool_name:\s*(\w+)', block, re.MULTILINE)
            tool_call_id = re.search(r'^tool_call_id:\s*(\S+)', block, re.MULTILINE)
            if tool_name and tool_call_id:
                messages.append(
                    ChatCompletionToolMessageParam(
                        role="tool",
                        tool_call_id=tool_call_id.group(1),
                        content=msg_content,
                    )
                )

    return messages
