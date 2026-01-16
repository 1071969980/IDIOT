#!/usr/bin/env python3
"""
Agent 最小化运行测试脚本

使用方法:
    python scripts/standalone_agent/agent_test.py --messages test_messages.md --tools todo_write
    python scripts/standalone_agent/agent_test.py --messages test_messages.md --tools read_file write_file edit_file
    python scripts/standalone_agent/agent_test.py --messages test_messages.md --tools todo_write --overwrite

参数说明:
    --messages: Markdown 消息文件路径（必需）
    --tools: 要启用的工具列表
    --service: LLM 服务名称（默认: deepseek-chat）
    --overwrite: 将输出覆盖到输入文件（默认为 False，输出到 .output.md 文件）
    --no-verbose: 不打印实时输出

可用工具:
    - todo_write: 待办事项工具（本地文件系统存储）
    - read_file: 读取文件工具（本地文件系统，存储在 scripts/standalone_agent/FS/）
    - write_file: 写入文件工具（本地文件系统，存储在 scripts/standalone_agent/FS/）
    - edit_file: 编辑文件工具（本地文件系统，存储在 scripts/standalone_agent/FS/）
    - ask_user_offline_cli: 命令行用户交互工具（使用 input() 获取用户输入）

输出文件:
    - 默认输出: {原消息文件名}.output.md
    - --overwrite 模式: 输出直接覆盖原输入文件

环境变量:
    - OPENAI_API_KEY: LLM API 密钥 (必需)
    - OPENAI_BASE_URL: LLM API 基础 URL (可选)
"""
import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from api.agent.strategy.main_agent import MainAgent

# 将 tools 目录添加到 Python 路径
SCRIPT_DIR = Path(__file__).parent
TOOLS_DIR = SCRIPT_DIR / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from api.agent.tools.todo.config_data_model import TodoWriteConfig
from api.agent.tools.todo.constructor import construct_todo_write
from api.agent.tools.file_operations.read_file.config_data_model import ReadFileConfig
from api.agent.tools.file_operations.read_file.constructor import construct_read_file
from api.agent.tools.file_operations.edit_file.config_data_model import EditFileConfig
from api.agent.tools.file_operations.edit_file.constructor import construct_edit_file
from api.agent.tools.file_operations.write_file.config_data_model import WriteFileConfig
from api.agent.tools.file_operations.write_file.constructor import construct_write_file
from api.testing.message_parser import parse_markdown_messages

# 导入离线版 ask_user 工具
from tools.ask_user_offline_cli.constructor import construct_ask_user_offline_cli
from tools.ask_user_offline_cli.config_data_model import AskUserOfflineCliConfig
from api.testing.message_serializer import save_messages
from api.testing.mock_streaming_processor import MockStreamingProcessor
from api.app.graceful_shutdown import (
    set_following_task_for_graceful_shutdown,
    wait_background_task_for_graceful_shutdown,
)

# 文件操作工具的本地存储目录（相对于脚本所在目录）
SCRIPT_DIR = Path(__file__).parent
FS_BASE_PATH = SCRIPT_DIR / "FS"
TODO_STORAGE = SCRIPT_DIR / "TODO_STORAGE"

# 工具注册表
AVAILABLE_TOOLS = {
    "todo_write": construct_todo_write,
    "read_file": construct_read_file,
    "edit_file": construct_edit_file,
    "write_file": construct_write_file,
    "ask_user": construct_ask_user_offline_cli,
}


async def main():
    parser = argparse.ArgumentParser(description="Agent 最小化运行测试")
    parser.add_argument("--messages", required=True, help="Markdown 消息文件路径")
    parser.add_argument("--tools", nargs="+", default=[], help="要启用的工具列表")
    parser.add_argument("--service", default="deepseek-chat", help="LLM 服务名称")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="将输出覆盖到输入文件（默认为 False，输出到 .output.md 文件）"
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

    # 确保存储目录存在
    file_tools_requested = any(t in ["read_file", "edit_file", "write_file"] for t in args.tools)
    if file_tools_requested:
        FS_BASE_PATH.mkdir(parents=True, exist_ok=True)
        print(f"📁 文件操作工具使用目录: {FS_BASE_PATH}")

    todo_requested = "todo_write" in args.tools
    if todo_requested:
        TODO_STORAGE.mkdir(parents=True, exist_ok=True)
        print(f"📁 Todo 工具使用目录: {TODO_STORAGE}")

    for tool_name in args.tools:
        if tool_name not in AVAILABLE_TOOLS:
            print(f"⚠️  未知工具: {tool_name}")
            continue

        # 使用本地文件系统存储
        if tool_name == "todo_write":
            config = TodoWriteConfig(
                enabled=True,
                storage_backend="local",
                local_base_path=str(TODO_STORAGE)
            )
            tool_param, tool_closure = AVAILABLE_TOOLS[tool_name](
                config=config, session_id=session_id
            )
            tools.append(tool_param)
            tool_functions[tool_name] = tool_closure
            print(f"✓ 加载工具: {tool_name} (本地文件: {TODO_STORAGE})")

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

        # ask_user 工具 - 命令行交互
        elif tool_name == "ask_user":
            config = AskUserOfflineCliConfig(enabled=True)
            tool_param, tool_closure = AVAILABLE_TOOLS[tool_name](
                config=config, session_id=session_id
            )
            tools.append(tool_param)
            tool_functions[tool_name] = tool_closure
            print(f"✓ 加载工具: {tool_name}")

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
        with set_following_task_for_graceful_shutdown():
            agent_memories, agent_messages = await agent.run(memories, args.service)

    # 等待后台任务优雅终止
    await wait_background_task_for_graceful_shutdown()

    print("=" * 60)
    print("\n✅ Agent 运行完成")

    # 5. 输出结果
    # 直接从 agent._runtime_memories 保存完整的运行时记忆（包含 reasoning_content 和 tool_calls）
    if args.overwrite:
        output_path = messages_path
    else:
        output_path = messages_path.parent / f"{messages_path.stem}.output.md"

    save_messages(agent._runtime_memories, str(output_path))
    print(f"📁 对话消息已保存到: {output_path}")

    # 打印统计
    print(f"\n📊 统计:")
    print(f"  - Agent 记忆数: {len(agent_memories)}")
    print(f"  - Agent 消息数: {len(agent_messages)}")


if __name__ == "__main__":
    asyncio.run(main())
