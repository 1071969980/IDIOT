# CLAUDE.md

本文件为在此代码库中工作时提供指导。

## 项目概述

IDIOT (Intelligent Development Integrated & Operations Toolkit) 是一个基于 Python 的 AI 应用程序后端工具包。

## 开发环境
   
### Python 环境
- **Python 版本**: 需要 3.13+
- **包管理器**: uv (Astral UV)
- **环境设置**: 
  ```bash
  uv python install 3.13
  uv sync
  ```

#### 临时测试用途的 python 脚本

请在项目目录使用 `uv run python -c` 或 `uv run script.py` 运行临时脚本。

## 日志记录

优先使用 **logfire** 进行分布式追踪，参考 `docs/for_LLM_dev/logfire日志记录实践指南.md`。

### 基本用法

```python
import logfire

# 追踪函数执行
with logfire.span("模块路径::函数名", attr1="value1", attr2="value2"):
    # 业务逻辑
    pass

# 日志级别
logfire.info("正常节点")
logfire.warning("可恢复异常")
logfire.error("不可恢复错误")
```

### Trace 上下文（set_baggage）

`set_baggage` 用于设置 Langfuse Trace 级别属性，在平台中按 user/session 聚合追踪数据。

```python
from api.logger.datamodel import LangFuseTraceAttributes

# 仅在涉及 user_id 或 session_id 时使用
trace_attrs = LangFuseTraceAttributes(
    name="trace_name",
    user_id=str(user_id),
    session_id=str(session_id),
)
with logfire.set_baggage(**trace_attrs.model_dump(mode="json", by_alias=True)):
    with logfire.span("operation"):
        pass
```

**注意**: 无 user/session 上下文时，直接使用 `logfire.span()` 即可，无需 `set_baggage`。

### 装饰器方式

```python
from api.logger.logger import log_span

@log_span("操作描述", args_captured_as_tags=['param_name'])
async def my_function(param_name: str):
    pass
```

### 选择原则

- **logfire.span**: 追踪执行流程、跨函数调用链
- **logfire.set_baggage**: 需要 user/session 聚合时使用
- **loguru**: 本地调试、文件操作、连接管理
