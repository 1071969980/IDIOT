# Standalone Agent

一个独立的 Agent 测试工具，可以在不启动完整系统（PostgreSQL、Redis、LLM 服务）的情况下运行和测试 Agent。

## 特性

- **无外部依赖** - 工具使用内存存储，无需数据库和 Redis
- **Markdown 格式** - 输入输出使用人类易读的 Markdown 格式
- **多轮对话** - 支持手动多轮对话，输出可直接拼接到下一轮输入
- **可编辑** - 每轮对话都可以手动编辑和调整

## 文件说明

| 文件 | 说明 |
|------|------|
| `agent_test.py` | 主测试脚本 |
| `test_messages.md` | 示例消息文件 |

## 使用方法

### 基本用法

```bash
# 运行一轮对话
python agent_test.py --messages test_messages.md --tools todo_write
```

### 手动多轮对话

```bash
# 第一轮
python agent_test.py --messages round1.md --tools todo_write --conversation-output round1_resp.md

# 手动将 round1_resp.md 追加到 round1.md，添加新用户消息，保存为 round2.md

# 第二轮
python agent_test.py --messages round2.md --tools todo_write --conversation-output round2_resp.md
```

### 输出模式对比

| 参数 | 输出内容 | 用途 |
|------|----------|------|
| `--output` | 包含所有消息（status, tool_call, assistant 等） | 调试、查看完整日志 |
| `--conversation-output` | 只含对话消息（assistant, tool），无 timestamp | 拼接到下一轮输入 |

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

| 工具 | 无依赖模式 |
|------|-----------|
| `todo_write` | ✅ 支持（内存存储） |

## 开发相关

- **实现位置**: `api/testing/`
- **核心组件**:
  - `MockStreamingProcessor` - Mock 流式处理器
  - `parse_markdown_messages()` - Markdown 消息解析器
  - `MessageBuilder` / `MarkdownBuilder` - 消息构造器
