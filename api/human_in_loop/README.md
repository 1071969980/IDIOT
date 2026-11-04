# Human-in-the-Loop (HIL) 模块

本模块实现 AI Agent 执行过程中暂停并向用户发起交互、等待回复或发送单向通知的机制。

## 架构概览

```
┌──────────────────┐    session_event_stream:{session_id}   ┌──────────────────┐
│   Agent 侧       │ ────────────────────────────────────> │  会话级 SSE      │
│  interrupt()     │                                       │  /chat/          │
│  notification()  │ <──────────────────────────────────── │  session_streaming│
└──────────────────┘    human_in_loop_recv_stream:{task_id} └──────────────────┘
          ▲                                                        │
          └──────────────── POST /hil/respond ◄───────────────────┘
                           POST /hil/ack_notification
```

- **下行**：HIL 中断/通知构造为统一事件，写入 `session_event_stream:{session_id}`，由会话级 SSE 推送给前端。
- **上行**：用户回复通过 `/hil/respond` 原子转换状态并写入 `human_in_loop_recv_stream:{session_task_id}`，唤醒等待中的 `interrupt()`。
- **状态**：`hil_interaction_state:{session_id}` Hash 保存每个 `msg_id` 的 `pending|responded|acked + expires_at`，用于历史回放过滤和并发控制。
- **单一会话流**：HIL 下行直接写入会话级事件 Stream。

## 核心组件

### 1. `data_model.py` — 中立领域模型

定义 `HILInterruptContent`、`HILNotificationContent` 及其内容体。所有模型使用 `extra="forbid"`，既作为 HIL 事件 payload 的 `content`，也由 Agent 工具构造。

### 2. `interrupt.py` — 中断与等待回复

`interrupt()` 的核心流程：

1. 生成 `msg_id`，构造 `hil.HIL_interrupt_request` 事件；
2. 通过 `publish_session_stream_event()` 原子写入会话 Stream 并登记 pending 状态；
3. 启动 60 秒租约心跳，刷新 pending `expires_at`、状态 Hash TTL 和会话 Stream TTL；
4. 循环读取 `human_in_loop_recv_stream:{session_task_id}` 的 JSON 响应，跳过其他 `msg_id`；
5. 业务总超时由 `time.monotonic()` 控制；
6. 超时抛 `HILInterruptTimeout`，取消抛 `HILInterruptCancelled`，并 best-effort 清理 pending 状态。

```python
from uuid import UUID
from api.human_in_loop.interrupt import interrupt, HILInterruptContent

result = await interrupt(
    content=HILInterruptContent(source="agent_tool_call", body=...),
    session_id=session_id,
    session_task_id=session_task_id,
    branch_name="main",
)
```

**项目中的使用**：`api/agent/tools/ask_user/constructor.py` 中的 `AskUserChoiceTool` 调用 `interrupt()`。

### 3. `notification.py` — 单向通知

`notification()` 构造 `hil.Notification` 事件并写入会话 Stream，同时登记 pending 状态；用户通过 `/hil/ack_notification` 确认。

### 4. `interaction_service.py` — 上行领域服务

- `respond()`：pending → responded，并在同一 Lua 中写入 recv_stream；
- `ack_notification()`：pending → acked；
- 状态不存在或过期返回 `not_found`，已处理返回 `conflict`。

### 5. `http_worker/router.py` — HTTP 上行接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/hil/respond` | POST | 发送用户回复 |
| `/hil/ack_notification` | POST | 确认 Notification 已读 |

服务端按 `session_task_id` 查询任务并校验所有权，再从任务取得 `session_id` 调用交互服务。请求体没有 `session_id` 字段。

### 6. `execption.py` — 异常定义

- `HILInterruptCancelled`：中断被取消；
- `HILInterruptTimeout(HILInterruptCancelled)`：中断超过业务总超时。

## 前端协议

HIL 不提供独立 SSE 路由。前端只建立一条 `POST /api/chat/session_streaming` 连接，监听：

- `hil.HIL_interrupt_request`
- `hil.Notification`
- `hil.stream_end`

`hil.stream_end` 只表示当前任务的 HIL 信道结束，不关闭会话级 SSE。完整协议见 `docs/api/session_streaming.apib`。
