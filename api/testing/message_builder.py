"""
Helper functions for programmatically building Markdown messages.
"""
from pathlib import Path
from typing import Any

# 消息分隔符（与 message_parser.py 保持一致）
MESSAGE_SEPARATOR = "--#&%--"


class MessageBuilder:
    """Markdown 消息构造器"""

    @staticmethod
    def system(content: str) -> str:
        """构造系统消息"""
        return f"""{MESSAGE_SEPARATOR}
type: system
content: |
  {content}
{MESSAGE_SEPARATOR}"""

    @staticmethod
    def user(content: str) -> str:
        """构造用户消息"""
        return f"""{MESSAGE_SEPARATOR}
type: user
content: |
  {content}
{MESSAGE_SEPARATOR}"""

    @staticmethod
    def assistant(content: str) -> str:
        """构造助手消息"""
        return f"""{MESSAGE_SEPARATOR}
type: assistant
content: |
  {content}
{MESSAGE_SEPARATOR}"""

    @staticmethod
    def tool(tool_name: str, tool_call_id: str, content: str | dict) -> str:
        """构造工具消息"""
        if isinstance(content, dict):
            import ujson

            content = ujson.dumps(content, ensure_ascii=False)
        return f"""{MESSAGE_SEPARATOR}
type: tool
tool_name: {tool_name}
tool_call_id: {tool_call_id}
content: |
  {content}
{MESSAGE_SEPARATOR}"""


class MarkdownBuilder:
    """Markdown 文档构造器，支持批量添加消息"""

    def __init__(self):
        self.messages: list[str] = []

    def add_system(self, content: str) -> "MarkdownBuilder":
        """添加系统消息"""
        self.messages.append(MessageBuilder.system(content))
        return self

    def add_user(self, content: str) -> "MarkdownBuilder":
        """添加用户消息"""
        self.messages.append(MessageBuilder.user(content))
        return self

    def add_assistant(self, content: str) -> "MarkdownBuilder":
        """添加助手消息"""
        self.messages.append(MessageBuilder.assistant(content))
        return self

    def add_tool(
        self, tool_name: str, tool_call_id: str, content: str | dict
    ) -> "MarkdownBuilder":
        """添加工具消息"""
        self.messages.append(MessageBuilder.tool(tool_name, tool_call_id, content))
        return self

    def build(self) -> str:
        """构建完整的 Markdown 文档"""
        return "\n\n".join(self.messages)

    def save(self, filepath: str) -> None:
        """保存到文件"""
        Path(filepath).write_text(self.build(), encoding="utf-8")


# 使用示例
def create_simple_conversation() -> str:
    """创建简单对话示例"""
    return (
        MarkdownBuilder()
        .add_system(
            "You are a helpful assistant with todo management capabilities."
        )
        .add_user("请帮我创建一个 todo，标题是'学习 Python'")
        .build()
    )


def create_multi_turn_conversation() -> str:
    """创建多轮对话示例"""
    return (
        MarkdownBuilder()
        .add_system("You are a helpful assistant.")
        .add_user("帮我创建两个 todo")
        .add_assistant("好的，请告诉我这两个 todo 的标题")
        .add_user("第一个是'学习 Python'，第二个是'学习 AsyncIO'")
        .build()
    )


def create_tool_conversation() -> str:
    """创建包含工具调用的对话示例"""
    return (
        MarkdownBuilder()
        .add_system(
            "You are a helpful assistant with todo management capabilities."
        )
        .add_user("请帮我创建一个 todo，标题是'测试 Agent'")
        .add_tool(
            "todo_write",
            "call_test_123",
            {"action": "create", "title": "测试 Agent", "status": "pending"},
        )
        .build()
    )
