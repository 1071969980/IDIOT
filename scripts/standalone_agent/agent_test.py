#!/usr/bin/env python3
"""
Agent 最小化运行测试脚本

使用方法:
    python scripts/standalone_agent/agent_test.py --messages test_messages.md --tools todo_write
    python scripts/standalone_agent/agent_test.py --messages test_messages.md --tools read_file write_file edit_file
    python scripts/standalone_agent/agent_test.py --messages test_messages.md --tools todo_write --append

参数说明:
    --messages: Markdown 消息文件路径（必需）
    --tools: 要启用的工具列表
    --service: LLM 服务名称（默认: deepseek-chat）
    --output: 输出完整日志文件路径（可选）
    --append: 自动将结果追加到原消息文件末尾（用于多轮对话）
    --no-verbose: 不打印实时输出

可用工具:
    - todo_write: 待办事项工具（内存存储）
    - read_file: 读取文件工具（本地文件系统，存储在 scripts/standalone_agent/FS/）
    - write_file: 写入文件工具（本地文件系统，存储在 scripts/standalone_agent/FS/）
    - edit_file: 编辑文件工具（本地文件系统，存储在 scripts/standalone_agent/FS/）

输出文件:
    - 默认输出: {原消息文件名}.output.md（对话消息，可用于下一轮输入）
    --append 模式: 结果同时追加到原消息文件

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
from api.agent.tools.file_operations.read_file.config_data_model import ReadFileConfig
from api.agent.tools.file_operations.read_file.constructor import construct_read_file
from api.agent.tools.file_operations.edit_file.config_data_model import EditFileConfig
from api.agent.tools.file_operations.edit_file.constructor import construct_edit_file
from api.agent.tools.file_operations.write_file.config_data_model import WriteFileConfig
from api.agent.tools.file_operations.write_file.constructor import construct_write_file
from api.testing.message_parser import parse_markdown_messages
from api.testing.mock_streaming_processor import MockStreamingProcessor

# 文件操作工具的本地存储目录（相对于脚本所在目录）
SCRIPT_DIR = Path(__file__).parent
FS_BASE_PATH = SCRIPT_DIR / "FS"

# 工具注册表
AVAILABLE_TOOLS = {
    "todo_write": construct_todo_write,
    "read_file": construct_read_file,
    "edit_file": construct_edit_file,
    "write_file": construct_write_file,
}


async def main():
    parser = argparse.ArgumentParser(description="Agent 最小化运行测试")
    parser.add_argument("--messages", required=True, help="Markdown 消息文件路径")
    parser.add_argument("--tools", nargs="+", default=[], help="要启用的工具列表")
    parser.add_argument("--service", default="deepseek-chat", help="LLM 服务名称")
    parser.add_argument("--output", help="输出日志文件路径 (Markdown，包含内部消息)")
    parser.add_argument(
        "--append", action="store_true",
        help="自动将结果追加到原消息文件末尾（用于多轮对话）"
    )
    parser.add_argument(
        "--no-verbose", action="store_true", help="不打印实时输出"
    )

    args = parser.parse_args()

    # 1. 解析消息
    messages_path = Path(args.messages)
    print(f"📄 读取消息文件: {messages_path}")
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

    # 确保文件系统目录存在
    file_tools_requested = any(t in ["read_file", "edit_file", "write_file"] for t in args.tools)
    if file_tools_requested:
        FS_BASE_PATH.mkdir(parents=True, exist_ok=True)
        print(f"📁 文件操作工具使用目录: {FS_BASE_PATH}")

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

        # 文件操作工具 - 使用本地文件后端
        elif tool_name in ["read_file", "edit_file", "write_file"]:
            if tool_name == "read_file":
                config = ReadFileConfig(
                    enabled=True,
                    storage_backend="local",
                    local_base_path=str(FS_BASE_PATH)
                )
            elif tool_name == "edit_file":
                config = EditFileConfig(
                    enabled=True,
                    storage_backend="local",
                    local_base_path=str(FS_BASE_PATH)
                )
            elif tool_name == "write_file":
                config = WriteFileConfig(
                    enabled=True,
                    storage_backend="local",
                    local_base_path=str(FS_BASE_PATH)
                )

            tool_param, tool_closure = AVAILABLE_TOOLS[tool_name](
                config=config, session_id=session_id
            )
            tools.append(tool_param)
            tool_functions[tool_name] = tool_closure
            print(f"✓ 加载工具: {tool_name} (本地文件: {FS_BASE_PATH})")

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
    # 总是输出对话消息文件（默认输出到原消息文件同目录下的 .output.md）
    output_path = messages_path.parent / f"{messages_path.stem}.output.md"
    streaming_processor.save_conversation(str(output_path))
    print(f"📁 对话消息已保存到: {output_path}")

    # 如果指定了 --append，则将结果追加到原消息文件
    if args.append:
        with open(messages_path, 'a', encoding='utf-8') as f:
            f.write(f"\n# Appended from {output_path.name}\n\n")
            with open(output_path, 'r', encoding='utf-8') as output_f:
                f.write(output_f.read())
        print(f"📁 结果已追加到原文件: {messages_path}")

    # 如果指定了 --output，则保存完整日志
    if args.output:
        streaming_processor.save_to_file(args.output)
        print(f"📁 完整日志已保存到: {args.output}")

    # 打印统计
    print(f"\n📊 统计:")
    print(f"  - 输出行数: {len(streaming_processor.output_lines)}")
    print(f"  - Agent 记忆数: {len(agent_memories)}")
    print(f"  - Agent 消息数: {len(agent_messages)}")


if __name__ == "__main__":
    asyncio.run(main())
