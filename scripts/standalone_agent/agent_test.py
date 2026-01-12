#!/usr/bin/env python3
"""
Agent 最小化运行测试脚本

使用方法:
    python scripts/agent_test.py --messages test_messages.md --tools todo_write

环境变量:
    - OPENAI_API_KEY: LLM API 密钥 (必需)
    - OPENAI_BASE_URL: LLM API 基础 URL (可选)
"""
import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from api.agent.strategy.main_agent import MainAgent
from api.agent.tools.todo.config_data_model import TodoWriteConfig
from api.agent.tools.todo.constructor import construct_todo_write
from api.testing.message_parser import parse_markdown_messages
from api.testing.mock_streaming_processor import MockStreamingProcessor

# 工具注册表
AVAILABLE_TOOLS = {
    "todo_write": construct_todo_write,
}


async def main():
    parser = argparse.ArgumentParser(description="Agent 最小化运行测试")
    parser.add_argument("--messages", required=True, help="Markdown 消息文件路径")
    parser.add_argument("--tools", nargs="+", default=[], help="要启用的工具列表")
    parser.add_argument("--service", default="deepseek-chat", help="LLM 服务名称")
    parser.add_argument("--output", help="输出日志文件路径 (Markdown，包含内部消息)")
    parser.add_argument(
        "--conversation-output",
        help="输出对话消息文件路径 (Markdown，只含对话消息，可用于下一轮输入)",
    )
    parser.add_argument(
        "--no-verbose", action="store_true", help="不打印实时输出"
    )

    args = parser.parse_args()

    # 1. 解析消息
    print(f"📄 读取消息文件: {args.messages}")
    memories = parse_markdown_messages(args.messages)

    print(f"✓ 加载了 {len(memories)} 条消息")

    # 2. 初始化组件
    task_uuid = uuid4()
    session_id = uuid4()
    user_id = uuid4()
    session_task_id = uuid4()

    streaming_processor = MockStreamingProcessor(
        task_uuid=task_uuid, verbose=not args.no_verbose
    )
    cancel_event = asyncio.Event()

    # 3. 准备工具
    tools = []
    tool_functions = {}

    for tool_name in args.tools:
        if tool_name not in AVAILABLE_TOOLS:
            print(f"⚠️  未知工具: {tool_name}")
            continue

        # 使用内存存储模式创建工具
        if tool_name == "todo_write":
            config = TodoWriteConfig(
                enabled=True, storage_backend="memory"  # 使用内存存储，无外部依赖
            )
            tool_param, tool_closure = AVAILABLE_TOOLS[tool_name](
                config=config, session_id=session_id
            )
            tools.append(tool_param)
            tool_functions[tool_name] = tool_closure
            print(f"✓ 加载工具: {tool_name} (内存存储)")

    if not tools:
        print("⚠️  没有加载任何工具")

    # 4. 运行 Agent
    print("\n🤖 启动 Agent...")
    print("=" * 60)

    agent = MainAgent(
        user_id=user_id,
        session_id=session_id,
        session_task_id=session_task_id,
        streaming_processor=streaming_processor,
        cancel_event=cancel_event,
        service_name=args.service,
        tools=tools,
        tool_call_function=tool_functions,
    )

    async with streaming_processor:
        agent_memories, agent_messages = await agent.run(memories, args.service)

    print("=" * 60)
    print("\n✅ Agent 运行完成")

    # 5. 输出结果
    if args.output:
        streaming_processor.save_to_file(args.output)
        print(f"📁 完整日志已保存到: {args.output}")

    if args.conversation_output:
        streaming_processor.save_conversation(args.conversation_output)
        print(f"📁 对话消息已保存到: {args.conversation_output}")

    # 打印统计
    print(f"\n📊 统计:")
    print(f"  - 输出行数: {len(streaming_processor.output_lines)}")
    print(f"  - Agent 记忆数: {len(agent_memories)}")
    print(f"  - Agent 消息数: {len(agent_messages)}")


if __name__ == "__main__":
    asyncio.run(main())
