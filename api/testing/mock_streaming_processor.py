"""
Mock StreamingProcessor for testing without Redis.

只负责流式输出和调试，不负责序列化文件。
"""
import asyncio
from datetime import datetime
from uuid import UUID
from typing import Any


class MockStreamingProcessor:
    """Mock 流式处理器，用于流式输出和调试"""

    def __init__(self, task_uuid: UUID, verbose: bool = True):
        self.task_uuid = task_uuid
        self.verbose = verbose  # 是否打印到控制台
        self._current_text = ""  # 当前累积的文本

    async def _log(self, msg_type: str, content: str = ""):
        """记录消息到输出"""
        # 添加时间戳
        timestamp = datetime.now().strftime("%H:%M:%S")

        if msg_type == "text_delta":
            # 文本增量直接累积
            self._current_text += content
            if self.verbose:
                print(content, end="", flush=True)
        else:
            # 其他消息类型输出 Markdown 格式
            lines = [
                "",
                "--#&%--",
                f"type: {msg_type}",
                f"timestamp: {timestamp}",
            ]
            if content:
                lines.append("content: |")
                lines.append("  " + content.replace("\n", "\n  "))
            lines.append("--#&%--")
            markdown = "\n".join(lines)
            if self.verbose:
                print(markdown)

    async def push_status_begin_msg(self, data: dict) -> None:
        import ujson
        await self._log("status_begin", ujson.dumps(data, ensure_ascii=False))

    async def push_status_update_msg(self, data: dict) -> None:
        import ujson
        await self._log("status_update", ujson.dumps(data, ensure_ascii=False))

    async def push_status_end_msg(self, data: dict) -> None:
        import ujson
        await self._log("status_end", ujson.dumps(data, ensure_ascii=False))

    async def push_text_start_msg(self) -> None:
        self._current_text = ""
        await self._log("text_start")

    async def push_text_end_msg(self) -> None:
        # 输出完整的文本消息
        if self._current_text:
            await self._log("assistant", self._current_text)
            self._current_text = ""
        else:
            await self._log("text_end")

    async def push_text_delta_msg(self, delta: str) -> None:
        await self._log("text_delta", delta)

    async def push_tool_call_msg(self, tool_exec_uuid: UUID, tool_name: str) -> None:
        content = f"tool: {tool_name}\ncall_id: {tool_exec_uuid}"
        await self._log("tool_call", content)

    async def push_tool_response_msg(self, tool_exec_uuid: UUID, tool_result: Any) -> None:
        import ujson
        result_str = str(tool_result)
        if hasattr(tool_result, "model_dump_json"):
            result_str = tool_result.model_dump_json()
        elif hasattr(tool_result, "json_content") and tool_result.json_content:
            result_str = ujson.dumps(tool_result.json_content, ensure_ascii=False)
        await self._log("tool_response", result_str)

    async def push_exception_ending_message(self, e: Exception) -> None:
        await self._log("exception", str(e))

    async def push_ending_message(self) -> None:
        await self._log("stream_end")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
