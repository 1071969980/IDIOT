# 02 系统提示词渲染链

## 概述

系统提示词是 Agent 上下文中优先级最高、最先注入的文本信息。它通过 `render_system_prompt()` 函数从 `SessionSystemPromptConfig` 渲染而来，最终作为 `role="system"` 的消息发送给 LLM。

## 入口

```
process_pending_messages.py:171
  → system_prompt = render_system_prompt(session_config.system_prompt_config)
```

## 渲染引擎

**文件**: `api/chat/render_system_prompt.py`

### 处理流程

```
SessionSystemPromptConfig
        │
        ▼
  ① 白/黑名单过滤 (whitelist / blacklist)
        │
        ▼
  ② 按 index 排序
        │
        ▼
  ③ 逐个渲染 prompt_def (根据类型分派)
        │
        ▼
  ④ 用 "\n" 拼接所有渲染结果
        │
        ▼
  返回: str (最终系统提示词)
```

## 五种提示词定义类型

所有类型定义在 `api/agent/session_agent_config/config_data_model.py`，联合类型为 `SessionSystemPromptDefUnion`。

### 1. 纯文本 (`SessionSystemPromptDefByPlainText`)

| 字段 | 说明 |
|------|------|
| `type` | `"plain_text"` |
| `text` | 直接的文本字符串 |

直接返回 `text` 字段值，不做任何转换。

### 2. 变量 (`SessionSystemPromptDefByVariable`)

| 字段 | 说明 |
|------|------|
| `type` | `"variable"` |
| `variable_name` | 变量名 |

从 `render_system_prompt()` 调用时传入的 `**variables` 参数中按名称取值。

### 3. LangFuse 提示词 (`SessionSystemPromptDefByLangFuse`)

| 字段 | 说明 |
|------|------|
| `type` | `"langfuse"` |
| `prompt_path` | LangFuse 中的提示词路径 (PurePosixPath) |
| `production` | 是否使用生产版本 (默认 True) |
| `label` | 标签版本 (可选) |
| `version` | 版本号 (可选) |
| `params` | 嵌套参数 (可选，值为 SessionSystemPromptDefUnion) |

**处理函数**: `get_prompt_from_langfuse()`，位于 `api/prompt_template/langfuse_prompt_template/constant.py`

**默认配置**中的主 Agent 系统提示词使用此类型：
- 路径: `"main_agent/system_prompt"`
- 版本: production

### 4. Jinja 模板文件 (`SessionSystemPromptDefByJinja`)

| 字段 | 说明 |
|------|------|
| `type` | `"jinja"` |
| `template_rel_path` | 相对于 Jinja 模板根目录的路径 (PurePosixPath) |
| `params` | 模板参数 (可选，值为 SessionSystemPromptDefUnion 或 Any) |

**模板环境**: `JINJA_ENV`，位于 `api/prompt_template/jinja_prompt_template/constant.py`
**模板根目录**: `api/prompt_template/jinja_prompt_template/`

### 5. Jinja 模板字符串 (`SessionSystemPromptDefByJinjaString`)

| 字段 | 说明 |
|------|------|
| `type` | `"jinja_string"` |
| `template` | Jinja 模板字符串 |
| `params` | 模板参数 (可选) |

直接在配置中内联 Jinja 模板，无需外部文件。

## 嵌套参数渲染

LangFuse、Jinja 类型的 `params` 支持嵌套 `SessionSystemPromptDefUnion`，即参数值本身可以是上述五种类型之一。渲染时会递归处理。

## 配置来源

### 默认配置

**文件**: `api/agent/session_agent_config/constants.py`

```python
DEFAULT_MAIN_AGENT_SYSTEM_PROMPT_CONFIG = SessionSystemPromptConfig(
    prompt_defs=[
        SessionSystemPromptDef(
            type="langfuse",
            prompt_path="main_agent/system_prompt",
            production=True,
        )
    ]
)
```

### 数据库配置

通过 `get_session_config_by_session_id()` 从 `u2a_session_agent_config` 表读取。

### 覆盖层机制

Task 的 `storage_snapshot` 中可包含 `session_config_overlay` 键，用于在运行时修改配置（包括系统提示词配置）。详见 [07_session_config.md](./07_session_config.md)。

## 数据流图

```
u2a_session_agent_config 表 (base config)
        │
        ▼
get_session_config_by_session_id()
        │
        ▼
SessionAgentConfig.model_validate()
        │
        ├── version 兼容性检查
        │
        ▼
storage_snapshot["session_config_overlay"]  ──→  deep_update_dict()
        │                                           │
        └───────────────────────────────────────────┘
                        │
                        ▼
            最终 SessionAgentConfig
                        │
                        ▼
            session_config.system_prompt_config
                        │
                        ▼
            render_system_prompt()
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
     LangFuse API   Jinja Env   plain_text/variable
           │            │            │
           └────────────┼────────────┘
                        ▼
                str (系统提示词)
                        │
                        ▼
          ChatCompletionSystemMessageParam(role="system")
                        │
                        ▼
                  Agent._system_mem
```

## 相关文件索引

| 文件 | 职责 |
|------|------|
| `api/chat/render_system_prompt.py` | 渲染引擎主文件 |
| `api/agent/session_agent_config/config_data_model.py` | 数据模型定义 |
| `api/agent/session_agent_config/constants.py` | 默认配置常量 |
| `api/agent/session_agent_config/crud.py` | 配置 CRUD 操作 |
| `api/prompt_template/langfuse_prompt_template/constant.py` | LangFuse 提示词获取 |
| `api/prompt_template/jinja_prompt_template/constant.py` | Jinja 模板环境 |
