# Standalone Agent

一个独立的 Agent 测试工具，可以在不启动完整系统（PostgreSQL、Redis、LLM 服务）的情况下运行和测试 Agent。

## 特性

- **无外部依赖** - 工具使用内存存储或本地文件系统，无需数据库和 Redis
- **Markdown 格式** - 输入输出使用人类易读的 Markdown 格式
- **自动输出** - 总是自动输出结果文件，无需手动指定
- **多轮对话** - 使用 `--append` 参数自动将结果追加到原消息文件

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

# 使用 --append 参数，结果自动追加到原消息文件（多轮对话）
python agent_test.py --messages test_messages.md --tools todo_write --append
```

### 输出文件说明

| 模式 | 输出文件 | 说明 |
|------|----------|------|
| 默认 | `{原消息文件名}.output.md` | 对话消息，自动生成 |
| `--append` | `{原消息文件名}.output.md` + 追加到原文件 | 结果同时追加到原消息文件 |
| `--output` | 指定路径 | 完整日志（包含所有消息） |

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

- **实现位置**: `api/testing/`
- **核心组件**:
  - `MockStreamingProcessor` - Mock 流式处理器
  - `parse_markdown_messages()` - Markdown 消息解析器
  - `MessageBuilder` / `MarkdownBuilder` - 消息构造器
