# 03 工具定义文本流

## 概述

工具定义以 `ChatCompletionToolParam` 格式作为 LLM API 调用的 `tools` 参数传入。每个工具携带名称、描述和参数 JSON Schema，这些文本信息构成了 Agent 能理解和使用工具的基础。

## 入口

```
process_pending_messages.py:187-197
  → tool_init_res, mcp_tools_loader = await init_tools(...)
```

## 工具初始化链

### init_tools()

**文件**: `api/chat/tool_init.py`

```
SessionAgentConfig.tools_config
        │
        ▼
  init_tools(user_id, session_id, session_task_id, session_config, ...)
        │
        ▼
  ToolFactory(session_id, session_task_id, user_id, ...)
        │
        ├── for each tool in tools_config:
        │     prepare_tool(name, config) → (ChatCompletionToolParam, ToolClosure)
        │
        ▼
  ToolInitializationResult
    ├── tool_completion_params_map: dict[str, ChatCompletionToolParam]  # 工具定义
    ├── tool_closures_map: dict[str, ToolClosure]                       # 工具执行闭包
    ├── enable_tools_set: set[str]                                      # 已启用工具
    ├── disable_tools_set: set[str]                                     # 已禁用工具
    ├── explicit_tools_set: set[str]                                    # 显式工具（可见于LLM）
    └── implicit_tools_set: set[str]                                    # 隐式工具（后台使用）
```

## 工具定义的文本构成

每个 `ChatCompletionToolParam` 包含以下文本信息：

```python
{
    "type": "function",
    "function": {
        "name": str,           # 工具名称
        "description": str,    # 工具描述（Agent 理解工具用途的关键文本）
        "parameters": {        # JSON Schema，包含参数名、类型、描述
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
}
```

**这些文本直接进入 LLM 的上下文窗口**，占用 token。

## 内置工具清单

**注册表**: `api/agent/tools/tool_factory/tool_init_function.py`

| 工具名 | 构造函数 | 模块路径 | 说明 |
|--------|----------|----------|------|
| `ask_user` | `ASK_USER_CONSTRUCTOR` | `tools/ask_user/` | 向用户提问 |
| `todo_write` | `TODO_WRITE_CONSTRUCTOR` | `tools/todo/` | 写入 TODO 列表 |
| `read_file` | `READ_FILE_CONSTRUCTOR` | `tools/file_operations/` | 读取文件 |
| `edit_file` | `EDIT_FILE_CONSTRUCTOR` | `tools/file_operations/` | 编辑文件 |
| `write_file` | `WRITE_FILE_CONSTRUCTOR` | `tools/file_operations/` | 写入文件 |
| `list_directory` | `LIST_DIRECTORY_CONSTRUCTOR` | `tools/file_operations/` | 列出目录 |
| `move_file` | `MOVE_FILE_CONSTRUCTOR` | `tools/file_operations/` | 移动文件 |
| `copy_file` | `COPY_FILE_CONSTRUCTOR` | `tools/file_operations/` | 复制文件 |
| `delete_file` | `DELETE_FILE_CONSTRUCTOR` | `tools/file_operations/` | 删除文件 |
| `sub_agent` | `SUB_AGENT_CONSTRUCTOR` | `tools/sub_agent/` | 子代理调用 |
| `bash` | `BASH_CONSTRUCTOR` | `tools/bash/` | 执行 Bash 命令 |
| `load_skill` | `LOAD_SKILL_CONSTRUCTOR` | `tools/skills/` | 加载技能 |
| `unload_skill` | `UNLOAD_SKILL_CONSTRUCTOR` | `tools/skills/` | 卸载技能 |
| `feed_message` | `FEED_MESSAGE_CONSTRUCTOR` | `tools/feed_message/` | 投递外部消息 |

## 工具构造函数的通用结构

每个工具模块通常包含：

| 组件 | 说明 |
|------|------|
| `TOOL_NAME` | 工具名常量 |
| `*Config` (Pydantic Model) | 工具配置模型 (继承 `SessionToolConfigBase`) |
| `*ParamDefine` (Pydantic Model) | 工具参数定义 → 转为 JSON Schema |
| `*GENERATION_TOOL_PARAM` | 预定义的 `ChatCompletionToolParam` |
| `constructor()` | 构造函数，返回 `(ChatCompletionToolParam, ToolClosure)` |

以 `read_file` 为例：

```python
# api/agent/tools/file_operations/read_file/
READ_FILE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name="read_file",
        description="读取文件内容，支持从指定行开始读取、限制读取行数。输出自动包含行号...",
        parameters=turn_pydantic_model_to_json_schema(ReadFileParamDefine),
        parameters_example={"file_path": "src/main.py", "offset": 10, "limit": 50}
    )
)
```

## MCP 工具

### 加载流程

```
SessionAgentConfig.mcp_config
        │
        ▼
  load_mcp_tools(session_config.mcp_config, ...)
        │
        ▼
  McpToolsLoader (api/agent/tools/mcp/adapter.py)
        │
        ├── 连接 MCP 服务器
        ├── 获取工具列表
        │
        ▼
  McpToolWrapper (api/agent/tools/mcp/tool_mapper.py)
        │
        ├── 转换 MCP 工具为 OpenAI 格式
        │
        ▼
  ChatCompletionToolParam[]
```

### MCP 工具文本来源

| 文本信息 | 来源 |
|----------|------|
| 工具名 | MCP 工具原始名（可选加服务器前缀） |
| 工具描述 | MCP 工具原始描述 |
| 参数 Schema | MCP 工具的 inputSchema |

## 工具文本在 Agent 中的流转

```
ToolInitializationResult
        │
        ▼
session_chat_task() 传入 MainAgent
        │
        ▼
AgentBase.enable_explicit_tools_name  # 显式工具名列表
AgentBase.explicit_tools_completion_params  # 显式工具 ChatCompletionToolParam
AgentBase.enable_tools_closure  # 工具执行闭包
        │
        ▼
prepare_tool_params()  → 返回 list[ChatCompletionToolParam]
        │
        ▼
LLM API 调用: kwargs["tools"] = tools
```

**文件**: `api/agent/base_agent.py`

```python
# 行 276-280
tools = await self.prepare_tool_params()
if tools:
    kwargs["tools"] = tools
```

## 工具执行结果的文本回流

工具执行后，结果文本以 `role="tool"` 消息回流到 Agent 上下文：

```
ToolClosure() → ToolTaskResult
                    ├── str_content: str    # 文本结果 → ChatCompletionToolMessageParam
                    ├── json_content: dict  # 结构化数据（可选）
                    └── occur_error: bool   # 是否出错
        │
        ▼
ChatCompletionToolMessageParam(
    content=tool_result.str_content,
    role="tool",
    tool_call_id=...
)
        │
        ▼
memory_trails.append_to_marker() → 写入 Memory Trails
        │
        ▼
下一轮 LLM 调用可见
```

## 相关文件索引

| 文件 | 职责 |
|------|------|
| `api/chat/tool_init.py` | 工具初始化入口 |
| `api/agent/tools/tool_factory/tool_factory.py` | 工具工厂 |
| `api/agent/tools/tool_factory/tool_init_function.py` | 工具注册表 |
| `api/agent/tools/type.py` | ToolClosure 类型定义 |
| `api/agent/tools/data_model.py` | ToolTaskResult 等数据模型 |
| `api/agent/tools/mcp/adapter.py` | MCP 工具适配器 |
| `api/agent/tools/mcp/tool_mapper.py` | MCP 工具格式转换 |
| `api/agent/base_agent.py` | 工具参数准备与 LLM 调用 |
