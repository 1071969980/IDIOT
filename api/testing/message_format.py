"""
Markdown message format for Agent testing.

**消息格式规范：**

使用 `--#&%--` 作为消息分隔符（避免与常见内容冲突）。

## 格式示例

### 系统消息
--#&%--
type: system
content: |
  You are a helpful assistant.
--#&%--

### 用户消息
--#&%--
type: user
content: |
  Hello, please help me create a todo item.
--#&%--

### 助手消息
--#&%--
type: assistant
content: |
  I'll help you create a todo item.
  Please provide the title.
--#&%--

### 工具消息
--#&%--
type: tool
tool_name: todo_write
tool_call_id: call_123
content: |
  {"action": "create", "title": "Test todo"}
--#&%--

## 多消息示例

--#&%--
type: system
content: |
  You are a helpful AI assistant with access to a todo management tool.
  You can help users create, update, and delete todo items.
--#&%--

--#&%--
type: user
content: |
  请帮我创建一个 todo，标题是"测试 Agent 运行"
--#&%--
"""

# 消息分隔符
MESSAGE_SEPARATOR = "--#&%--"
