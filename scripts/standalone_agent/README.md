# Standalone Agent

一个独立的 Agent 测试工具，可以在不启动完整系统（PostgreSQL、Redis、LLM 服务）的情况下运行和测试 Agent。

## 特性

- **无外部依赖** - 工具使用内存存储或本地文件系统，无需数据库和 Redis
- **Markdown 格式** - 输入输出使用人类易读的 Markdown 格式
- **完整序列化** - 支持完整的消息字段（`reasoning_content`、`tool_calls`）
- **多轮对话** - 使用 `--overwrite` 参数直接覆盖输入文件实现多轮对话

## 文件说明

| 文件 | 说明 |
|------|------|
| `agent_test.py` | 主测试脚本 |
| `test_messages.md` | 示例消息文件 |
| `FS/` | 文件操作工具的本地存储目录（自动创建） |
| `TODO_STORAGE/` | Todo 工具的本地存储目录（自动创建） |

## 使用方法

### 环境配置

**工作目录**: 需要切换到 `scripts/standalone_agent/`

```bash
cd scripts/standalone_agent/
```

**必需环境变量**:
- `PYTHONPATH`: 设置为项目根目录，以便正确导入模块
- `OPENAI_API_KEY`: LLM API 密钥（必需）

**环境变量文件** (可选): 从 `docker/.env` 加载

### 命令行运行

```bash
# 设置环境变量并运行（Linux/macOS）
export PYTHONPATH="../../"
export OPENAI_API_KEY="your-api-key"

# 或从环境变量文件加载
source ../../docker/.env

# 运行测试（结果自动保存到 test_messages.output.md）
python agent_test.py --messages test_messages.md --tools todo_write

# 使用文件操作工具
python agent_test.py --messages test_messages.md --tools read_file write_file edit_file

# 使用 --overwrite 参数，结果直接覆盖原消息文件（多轮对话）
python agent_test.py --messages test_messages.md --tools todo_write --overwrite
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--messages` | Markdown 消息文件路径（必需） |
| `--tools` | 要启用的工具列表 |
| `--service` | LLM 服务名称（默认: deepseek-chat） |
| `--overwrite` | 将输出覆盖到输入文件（默认: False，输出到 `.output.md` 文件） |
| `--no-verbose` | 不打印实时输出 |

### 输出文件说明

| 模式 | 输出文件 | 说明 |
|------|----------|------|
| 默认 | `{原消息文件名}.output.md` | 完整的运行时记忆（包含所有消息） |
| `--overwrite` | `{原消息文件名}` | 直接覆盖原输入文件 |

### VS Code 调试

使用 `.vscode/launch.json` 中的 `standalone_agent` 配置即可直接调试。

配置已自动设置：
- `cwd`: `${workspaceFolder}/scripts/standalone_agent`
- `PYTHONPATH`: `${workspaceFolder}`
- `envFile`: `${workspaceFolder}/docker/.env`

## 消息格式

使用 `--#&%--` 作为消息分隔符：

```markdown
--#&%--
type: system
content: |
  You are a helpful AI assistant.
--#&%--

--#&%--
type: user
content: |
  请帮我创建一个 todo
--#&%--
```

### 支持的字段

| 消息类型 | 支持字段 |
|----------|----------|
| `system` | `content` |
| `user` | `content` |
| `assistant` | `content`, `reasoning_content`, `tool_calls` |
| `tool` | `content`, `tool_call_id` |

### 示例：带工具调用的 Assistant 消息

```markdown
--#&%--
type: assistant
content: |
  我会帮你创建这个 todo。
tool_calls: |
  [{"id": "call_abc123", "type": "function", "function": {"name": "todo_write", "arguments": "{\"title\": \"测试\"}"}}]
--#&%--
```

### 示例：带推理内容的 Assistant 消息

```markdown
--#&%--
type: assistant
content: |
  让我帮你创建一个 todo 项目。
reasoning_content: |
  用户想要创建待办事项，我应该调用 todo_write 工具。
--#&%--
```

## 支持的工具

| 工具 | 无依赖模式 | 存储位置 |
|------|-----------|----------|
| `todo_write` | ✅ 支持 | 本地文件系统 (`TODO_STORAGE/` 目录) |
| `read_file` | ✅ 支持 | 本地文件系统 (`FS/` 目录) |
| `write_file` | ✅ 支持 | 本地文件系统 (`FS/` 目录) |
| `edit_file` | ✅ 支持 | 本地文件系统 (`FS/` 目录) |

**存储说明**:
- 所有工具都使用本地文件系统后端，数据持久化存储
- 目录会在首次使用时自动创建
- Todo 工具存储在 `scripts/standalone_agent/TODO_STORAGE/todos.json`
- 文件操作工具使用相对路径，例如: `read_file` 读取 `test.txt` 相当于读取 `FS/test.txt`

## 开发相关

### 核心模块

| 模块 | 职责 |
|------|------|
| `message_serializer.py` | 将 `ChatCompletionMessageParam` 序列化为 Markdown 文件 |
| `message_parser.py` | 解析 Markdown 文件为 `ChatCompletionMessageParam` |
| `mock_streaming_processor.py` | 流式输出和调试（不负责序列化） |

### 设计原则

- **职责分离**: 序列化、解析、流式输出各司其职
- **完整数据**: 从 `agent._runtime_memories` 直接序列化，不丢失任何字段
- **简单直接**: 每个模块只做一件事，做好一件事
