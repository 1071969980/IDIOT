"""
Parse Markdown messages to ChatCompletionMessageParam format.

支持完整的消息字段解析，包括 reasoning_content 和 tool_calls。
"""
import re
import ujson
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

    支持以下字段：
    - type: 消息类型（system/user/assistant/tool）
    - content: 消息内容
    - reasoning_content: 推理内容（assistant 消息）
    - tool_calls: 工具调用列表（assistant 消息，JSON 格式）
    - tool_call_id: 工具调用 ID（tool 消息）

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
            r'^content:\s*\|(.*?)(?=^\w|\Z)', block, re.MULTILINE | re.DOTALL
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
            # 解析 reasoning_content
            reasoning_match = re.search(
                r'^reasoning_content:\s*\|(.*?)(?=^\w|\Z)',
                block, re.MULTILINE | re.DOTALL
            )
            reasoning_content = reasoning_match.group(1).strip() if reasoning_match else None

            # 解析 tool_calls（JSON 格式）
            tool_calls = None
            tool_calls_match = re.search(
                r'^tool_calls:\s*\|(.*?)(?=^\w|\Z)',
                block, re.MULTILINE | re.DOTALL
            )
            if tool_calls_match:
                try:
                    tool_calls = ujson.loads(tool_calls_match.group(1).strip())
                except (ujson.JSONDecodeError, ValueError):
                    tool_calls = None

            # 构建 assistant 消息
            assistant_msg: ChatCompletionAssistantMessageParam = (
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=msg_content,
                )
            )

            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content  # type: ignore

            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls  # type: ignore

            messages.append(assistant_msg)

        elif msg_type == "tool":
            tool_call_id = re.search(r'^tool_call_id:\s*(\S+)', block, re.MULTILINE)
            if tool_call_id:
                messages.append(
                    ChatCompletionToolMessageParam(
                        role="tool",
                        tool_call_id=tool_call_id.group(1),
                        content=msg_content,
                    )
                )

    return messages
