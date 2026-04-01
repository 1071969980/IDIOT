# Human-in-the-Loop (HIL) 模块

本模块实现了 AI Agent 执行过程中的"人工介入"机制，允许 Agent 在需要时暂停执行、向用户发起请求并等待回复，然后再继续执行。

## 架构概览

```
┌──────────────────┐       Redis Stream        ┌──────────────────┐
│   Agent 侧       │  (send_stream / recv_     │   用户侧         │
│   (后端任务)      │        stream)            │   (HTTP API)     │
│                  │ ◄───────────────────────► │                  │
│  interrupt()     │     pickle 序列化消息      │  long_poll_worker│
│  notification()  │                           │  HTTP 路由        │
└──────────────────┘                           └──────────────────┘
```

核心通信基于 **Redis Stream**，Agent 与用户之间通过两条 Stream 双向传递消息：
- **send_stream** (`human_in_loop_send_stream:{id}`): Agent → 用户方向
- **recv_stream** (`human_in_loop_recv_stream:{id}`): 用户 → Agent 方向

## 核心组件

### 1. `context.py` — 流生命周期管理

`HILMessageStreamContext` 是一个异步上下文管理器，负责创建和维护 Redis Stream 的生命周期：

- **进入时**: 创建 send/recv 两条空 Stream 并设置 TTL
- **运行中**: 后台守护协程定期刷新 TTL（默认 3600 秒），防止 Stream 过期
- **退出时**: 清理所有 Stream 并取消守护协程

支持同时管理多个 Stream（传入 `Iterable[str]`）。

```python
from api.human_in_loop.context import HILMessageStreamContext

async with HILMessageStreamContext(stream_identifier=str(session_task_id)):
    # 在此上下文内，Agent 可以发起 interrupt 等待用户回复
    ...
```

**项目中的使用**: `api/chat/chat_task.py` 在 `session_chat_task` 中为每个会话任务创建 HIL 上下文。

### 2. `interrupt.py` — 中断与等待回复

`interrupt()` 是 Agent 侧的核心函数，用于向用户发送请求并阻塞等待回复：

1. 检查 Redis Stream 是否存在
2. 将 `HILInterruptContent` 序列化后写入 send_stream
3. 阻塞等待 recv_stream 中的匹配回复
4. 支持超时重试（默认 3600 秒超时，最多重试 6 次）
5. 支持通过 `cancel_event` 外部取消

**消息内容模型**:
- `HILInterruptContent`: 中断请求的顶层模型，包含来源 (`source`) 和内容体 (`body`)
- `HILInterruptContentAgentToolCallBody`: 工具调用类中断，包含 `tool_name`、`type`、`tool_exec_uuid`、`detail`
- 目前支持的类型: `ChoiceForm`（选项表单）

```python
from api.human_in_loop.interrupt import interrupt, HILInterruptContent, HILInterruptContentAgentToolCallBody

result = await interrupt(
    content=HILInterruptContent(source="agent_tool_call", body=...),
    stream_identifier=str(session_task_id),
)
```

**项目中的使用**: `api/agent/tools/ask_user/constructor.py` 中的 `AskUserChoiceTool` 调用 `interrupt()` 实现"询问用户选择"工具。

### 3. `notification.py` — 单向通知

`notification()` 用于 Agent 向用户发送单向通知（不需要回复），模型结构与 `interrupt` 对齐：

**消息内容模型**:
- `HILNotificationContent`: 通知的顶层模型，包含来源 (`source`) 和内容体 (`body`)
- `HILNotificationContentAgentToolCallBody`: 工具调用类通知，包含 `tool_name`、`type`、`tool_exec_uuid`、`detail`
- 目前支持的类型: `Info`（信息通知）

```python
from api.human_in_loop.notification import notification, HILNotificationContent, HILNotificationContentAgentToolCallBody

await notification(
    content=HILNotificationContent(source="agent_tool_call", body=...),
    stream_identifier=str(session_task_id),
)
```

### 4. `http_worker/` — HTTP 长轮询接口

为前端提供 HTTP API，让用户通过长轮询获取 Agent 的中断请求并回复。

**路由** (`router.py`，前缀 `/hil`):

| 端点 | 方法 | 说明 |
|------|------|------|
| `/hil/poll` | POST | 长轮询获取 Agent 消息 |
| `/hil/respond` | POST | 发送用户回复 |

两个端点都需要认证。

**数据模型** (`data_model.py`):

- `HILPollRequest`: 轮询请求（session_task_id, timeout, redis_last_id）
- `HILPollResponse`: 轮询响应（redis_last_id, HIL_msg）
- `HILResponseRequest`: 用户回复（session_task_id, hil_msg_id, msg）

**`LongPollWorker`** (`long_poll_worker.py`): 核心轮询逻辑实现，负责从 Redis Stream 读取消息、反序列化、以及写入用户回复。

### 5. `execption.py` — 异常定义

- `HILMsgStreamMissingError`: Redis Stream 不存在或已过期
- `HILInterruptCancelled`: 中断被取消（超时或外部信号）

## 消息流转示例

以"询问用户选择"（AskUserChoice）为例：

```
1. chat_task 创建 HILMessageStreamContext(session_task_id)
2. Agent 调用 ask_user_choice 工具
3. AskUserChoiceTool 构造 HILInterruptContent，调用 interrupt()
4. interrupt() 将消息写入 send_stream，阻塞等待
5. 前端 POST /hil/poll 获取到该消息
6. 用户在前端做出选择
7. 前端 POST /hil/respond 发送回复
8. LongPollWorker 将回复写入 recv_stream
9. interrupt() 收到回复，返回结果给 Agent
10. Agent 继续执行
```
