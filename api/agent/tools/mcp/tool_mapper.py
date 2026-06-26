"""
MCP 工具映射到 Agent 工具
"""

import asyncio
from contextlib import suppress
from typing import Any
from uuid import UUID

from mcp.types import Tool as McpTool, CallToolResult
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from api.agent.tools.data_model import ToolTaskResult
from .client import McpServerConnection

class McpToolWrapper:
    """
    MCP 工具包装器

    将 MCP 工具调用转换为 ToolClosure，并处理结果转换。
    """

    def __init__(
        self,
        mcp_tool: McpTool,
        connection: McpServerConnection,
        tool_name_prefix: str = ""
    ):
        self.mcp_tool = mcp_tool
        self.connection = connection
        self.tool_name_prefix = tool_name_prefix

    def get_full_name(self) -> str:
        """获取工具完整名称"""
        return f"{self.tool_name_prefix}{self.mcp_tool.name}" \
            if self.tool_name_prefix else self.mcp_tool.name

    def get_tool_param(self) -> ChatCompletionToolParam:
        """生成 OpenAI 工具参数"""
        full_name = f"{self.tool_name_prefix}{self.mcp_tool.name}" \
            if self.tool_name_prefix else self.mcp_tool.name

        return ChatCompletionToolParam(
            type="function",
            function=FunctionDefinition(
                name=full_name,
                description=self.mcp_tool.description or "",
                parameters=self._convert_input_schema()
            )
        )

    def _convert_input_schema(self) -> dict:
        """
        转换 MCP inputSchema 为 OpenAI 格式

        MCP 的 inputSchema 已经是 JSON Schema 格式，
        只需移除一些 OpenAI 不支持的字段。
        """
        schema = dict(self.mcp_tool.inputSchema)

        # 移除 OpenAI 不支持的字段
        schema.pop("$schema", None)
        schema.pop("$id", None)

        return schema

    async def __call__(self, exec_uuid: UUID, cancel_event: asyncio.Event, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        执行工具调用

        Args:
            exec_uuid: 执行 UUID，该参数与 api/agent/base_agent.py 的调用约定一致
            cancel_event: 取消事件，该参数与 api/agent/base_agent.py 的调用约定一致
            **kwargs: LLM 传递的参数

        Returns:
            ToolTaskResult: 执行结果
        """
        # 快速返回：已被取消
        if cancel_event.is_set():
            return ToolTaskResult(
                str_content=f"MCP 工具调用已被用户取消 ({self.mcp_tool.name})",
                occur_error=True,
            )

        try:
            # 并发竞争：call_tool vs cancel_event
            call_task = asyncio.create_task(
                self.connection.call_tool(self.mcp_tool.name, kwargs)
            )
            cancel_task = asyncio.create_task(cancel_event.wait())
            _done, pending = await asyncio.wait(
                [call_task, cancel_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

            if cancel_event.is_set():
                return ToolTaskResult(
                    str_content=f"MCP 工具调用已被用户取消 ({self.mcp_tool.name})",
                    occur_error=True,
                )

            result = call_task.result()
            return self._convert_result(result)

        except Exception as e:
            return ToolTaskResult(
                str_content=f"MCP 工具调用失败 ({self.mcp_tool.name}): {str(e)}",
                occur_error=True
            )

    def _convert_result(self, mcp_result: CallToolResult) -> ToolTaskResult:
        """
        转换 MCP 结果为 ToolTaskResult

        Args:
            mcp_result: MCP 返回的结果

        Returns:
            ToolTaskResult: 转换后的结果
        """
        content_parts = []

        for content_item in mcp_result.content:
            if hasattr(content_item, "text"):
                content_parts.append(content_item.text)
            elif hasattr(content_item, "data"):
                # 处理二进制数据（如图片）
                content_parts.append(f"[Binary data: {len(content_item.data)} bytes]")
            else:
                content_parts.append(str(content_item))

        str_content = "\n".join(content_parts)

        # 检查是否有错误
        is_error = any(
            hasattr(item, "type") and item.type == "error"
            for item in mcp_result.content
        )

        return ToolTaskResult(
            str_content=str_content,
            json_content={"raw_response": mcp_result.model_dump()} if str_content else None,
            occur_error=is_error
        )
