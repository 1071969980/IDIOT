---
name: sse-session-event-bus-handoff
status: implementation-planning
updated: 2026-10-31
---

# SSE 会话级事件总线 handoff

## 0. 入口路径

按顺序完成下面三步，即可接手当前工作。

1. **读本档**
   - 先读第 1、2 节，确认当前阶段和下一步大任务。
   - 再读第 3–5 节，恢复最终架构、数据契约、writer 与 HIL 状态设计。
   - 详细决策索引见第 6 节；未决事项见第 9 节。

2. **验当前基线**
   ```bash
   cd /home/gmh/桌面/IDIOT
   git rev-parse --short HEAD
   git status --short
   grep -RIn 'prefix="/chat"\|prefix="/session_events"\|prefix="/hil"' api/app/chat api/human_in_loop
   ```
   本快照创建时预期：
   - HEAD 为 `ddb555b`；
   - 工作区除未跟踪的 `docs/ai_paradigm/` 和 `docs/handoff/` 外，不应有代码改动；
   - 三个旧 SSE 路由仍可定位。
   若 HEAD 或工作区状态已变化，先判断是正常推进还是快照已过时。

3. **进入当前工作**
   - 当前没有可执行的编码任务。
   - **下一步大任务：把实现拆成阶段，并为每个阶段编写实现计划。**
   - 阶段拆分和计划必须先经用户确认，再开始写代码。

## 1. 事件定位与进展

- **任务**：把三个 SSE 接口整合为一个会话级事件总线，并删除不再使用的旧 SSE 实现。
  - `POST /api/chat/streaming`
  - `POST /api/session_events/streaming`
  - `POST /api/hil/streaming`
- **范围**：一条连接负责一个 `session_id` 内的多个 `session_task_id`，不跨多个会话。
- **当前阶段**：架构、数据契约、writer 与 HIL 状态设计已确认；尚未开始实现。
- **代码状态**：无代码改动；只有本 handoff 和范式文档未跟踪。
- **下一步产出**：实施阶段拆分 + 每阶段实现计划，而不是代码。

## 2. 下一步大任务

**把实现拆成可独立验收的阶段，并为每个阶段编写实现计划。**

每个阶段的计划至少回答：

- 目标与交付物；
- 会触碰的代码/文档工件；
- 必须遵守的已确认约束；
- 阶段内验证方式；
- 阶段结束后的可观察状态；
- 与下一阶段的依赖关系。

阶段骨架见第 7 节；当前只是骨架，尚未形成可执行计划。

## 3. 最终架构

### 3.1 一条会话一条 SSE

```text
Session 事件 ─┐
Chat 事件    ├──> session_event_stream:{session_id} ──> 一条 SSE ──> 前端
HIL 事件     ┘
```

- 一条连接只对应一个 `session_id`；
- 连接跨该会话的多个任务持续存在；
- Session、Chat、HIL 共用一个 Redis Stream；
- Stream entry ID 同时作为 SSE 事件 ID；
- 续读只使用一个 `Last-Event-ID`；
- 请求体不携带游标，相同的请求体表示恢复同一条逻辑订阅；
- 任务结束只发送任务级/信道级结束事件，不关闭连接。

### 3.2 统一事件信封

```json
{
  "v": 1,
  "channel": "chat",
  "type": "text_msg_delta",
  "session_id": "01945a1b-...",
  "session_task_id": "01945a1b-...",
  "branch_name": "main",
  "payload": {
    "content": "你好"
  }
}
```

- SSE `event` 名：`channel.type`；
- Redis Stream entry：单个 `event` 字段保存完整 JSON；
- `payload` 必须是 JSON 对象，禁止 JSON 字符串套 JSON 字段；
- Stream entry ID 不写入事件体。

### 3.3 HIL 最终形态

```text
下行：Agent → session_event_stream:{session_id} → 会话级 SSE → 前端
上行：前端 → POST /hil/respond → human_in_loop_recv_stream:{task_id} → interrupt() 等待者
状态：hil_interaction_state:{session_id} (Hash)
  field: msg_id
  value: {state: pending|responded|acked, expires_at: <unix_ms>}
```

- HIL send_stream 删除；
- HIL 不双写；
- `/hil/respond` 与 `/hil/ack_notification` 通过 Lua 原子脚本校验并转换 `pending` 状态；
- 不存在/已过期返回 404，已处理返回 409；
- 暂不主动广播 `hil.interaction_resolved` 事件。

### 3.4 定时参数

```text
session_event_stream TTL          = 3600s，写入时刷新
hil_interaction_state key TTL     = 3600s
HIL 交互租约 expires_at           = 3600s
HIL 租约心跳间隔                  = 60s
interrupt() 业务总超时默认值       = 3600s，可由调用点覆盖
```

`interrupt()` 等待期间的心跳刷新：当前 HIL field 的 `expires_at`、状态 Hash TTL、会话 Stream TTL。Redis 租约只是故障兜底，不决定业务超时。

## 4. 数据契约

### 4.1 信封字段

```text
v                 Literal[1]
channel           session | chat | hil | system（system 暂保留）
type              事件类型
session_id        UUID
session_task_id   UUID（v1 业务事件必填）
branch_name       str | None
payload           对应事件的 Pydantic payload 模型
```

模型规则：

- 采用嵌套 discriminated union：先按 `channel`，再按 `type`；
- 信封与 payload 均 `extra="forbid"`；
- 每个事件独立定义 payload 类，空 payload 也独立定义；
- 程序内部传 Pydantic 对象，只在 Redis 边界序列化/反序列化一次。

### 4.2 当前事件目录

| channel | type | payload | 状态 |
|---|---|---|---|
| session | `branch_task_started` | `{}` | 已确认 |
| session | `branch_task_completed` | `{outcome, has_exception}` | 已确认 |
| chat | `text_msg_begin` | `{}` | 已确认 |
| chat | `text_msg_delta` | `{content: str}` | 已确认 |
| chat | `text_msg_end` | `{}` | 已确认 |
| chat | `reasoning_delta` | `{content: str}` | 已确认 |
| chat | `tool_call` | `{tool_exec_uuid, tool_name}` | 已确认 |
| chat | `tool_response` | `{tool_exec_uuid, tool_result}` | 已确认 |
| chat | `stream_end` | `{outcome, error}` | 已确认 |
| hil | `HIL_interrupt_request` | `{msg_id, content}` | 已确认 |
| hil | `Notification` | `{msg_id, content}` | 已确认 |
| hil | `stream_end` | `{}` | 已确认 |

- `chat.status_begin/update/end`：无业务调用，计划删除；
- `mem_recall_*`、`mem_write_*`：长期记忆能力不在路线图，计划删除；
- `chat.reasoning_delta`：用于流式发送 LLM 的推理内容（`reasoning_content`），当前生产代码仍在用，纳入 v1 事件目录；没有独立的 reasoning begin/end 事件。

### 4.3 控制帧

- `init`：SSE 端点直接发送；
- `: heartbeat`：空闲心跳注释；
- 游标过期注释：`Last-Event-ID` 早于最早可读事件时发送，随后从最近有效事件继续；
- 以上控制帧都不是 Redis Stream 业务事件。

## 5. Writer 与 HIL 状态

### 5.1 Writer 公共入口

```python
async def publish_session_stream_event(event: SessionStreamEvent) -> str:
    ...
```

- 内部按 `event.session_id` 从 `WeakValueDictionary` 懒加载 `SessionStreamWriter`；
- writer 不持有长期后台任务；
- 不加 per-session 串行锁；
- 成功返回 Stream entry ID，失败从公共入口抛出；
- 写入语义为 at-least-once。

### 5.2 重试

- 可重试：`redis.exceptions.ConnectionError`、`redis.exceptions.TimeoutError`；
- 不重试：Pydantic 校验错误、`DataError`、其他 `ResponseError`；
- 默认 3 次重试，退避 0.5s/1s/2s；
- 重试期间公共入口保持挂起；
- 序列化只执行一次。

### 5.3 写入策略

```text
普通事件：
  MULTI
    XADD session_event_stream:{session_id} * event <json>
    EXPIRE session_event_stream:{session_id} 3600
  EXEC

HIL 交互事件：
  Lua:
    XADD session_event_stream:{session_id} * event <json>
    HSET hil_interaction_state:{session_id} {msg_id} {pending + expires_at}
    EXPIRE session_event_stream:{session_id} 3600
    EXPIRE hil_interaction_state:{session_id} 3600
```

HIL 心跳需要内部 `refresh_session_stream_ttl(session_id)` 能力。

### 5.4 HIL 业务超时

- 旧 `interrupt(timeout=3600, timeout_retry=6, ...)` 中，`timeout_retry` 是旧等待轮数；历史上曾用于超时重发，后改为仅第一轮发送。该参数删除。
- 新语义：`timeout` 表示业务总超时，由调用点传入，并由内部单调时钟执行。
- 新增强议异常 `HILInterruptTimeout`，与 `HILInterruptCancelled` 区分。
- 超时/取消后停止心跳，并 best-effort 将 HIL 状态标记为过期或删除。

## 6. 已确认决策索引

> 只保留可执行约束。D007 已由 D012 解决；D029 已撤销。

| ID | 约束 |
|---|---|
| D001 | 前端连接建立时机可以修改，不视为固定约束。 |
| D002 | 会话事件只保证保留窗口内一定程度的续读，不承诺无限期补发。 |
| D003 | 单路业务故障不得关闭整条连接。 |
| D004 | 一条连接覆盖同一会话内的多个任务。 |
| D005 | 采用会话级事件总线方案。 |
| D006 | 一条连接只负责一个 `session_id`，不跨会话聚合。 |
| D008 | 三个旧 SSE 接口最终删除；验证通过前可容忍其失效，不承诺兼容。 |
| D009 | Session 事件从 Pub/Sub 迁移到 Redis Stream。 |
| D010 | Session、Chat、HIL 都支持一定程度 `Last-Event-ID` 续读。 |
| D011 | 三类事件共用一个会话级 Stream、一个事件 ID、一个游标。 |
| D012 | 游标早于最早可读事件时发 SSE 注释，再从最近有效事件继续。 |
| D013 | 请求体不含游标，语义幂等；续读只走 `Last-Event-ID`。 |
| D014 | 信封字段使用 `channel`，不使用 `source`。 |
| D015 | SSE 事件名使用 `channel.type`。 |
| D016 | Redis entry 用单个 `event` 字段保存完整 JSON；entry ID 即事件 ID。 |
| D017 | 保留现有 type 名称并加信道前缀；信道结束事件不等于连接结束；`system` 暂保留。 |
| D018 | `payload` 必须是 JSON 对象，禁止 JSON 字符串套 JSON 字段。 |
| D019 | Chat 文本组 payload：begin/end 为 `{}`，delta 为 `{content}`。 |
| D020 | 删除无业务调用的 Chat `status_*` 事件和 `push_status_*` 方法。 |
| D021 | 进行数据模型层改造：类型化信封和 payload，程序内部传对象。 |
| D022 | Chat 工具事件 payload：`{tool_exec_uuid, tool_name}` / `{tool_exec_uuid, tool_result}`。 |
| D023 | `chat.stream_end` payload 为 `{outcome, error}`。 |
| D024 | HIL 事件复用现有领域模型，payload 为 `{msg_id, content}`；响应事件不进入总线。 |
| D025 | 删除四个长期记忆 Session 事件及其发布调用。 |
| D026 | Session 仅保留 `branch_task_started/completed`；完成事件含 `outcome` 与 `has_exception`。 |
| D027 | 每个空 payload 事件使用独立 payload 类。 |
| D028 | 信封与 payload 使用 `extra="forbid"`。 |
| D030 | 删除 HIL send_stream；下行用会话 Stream，上行保留 recv_stream；状态用每会话 Hash。 |
| D031 | `/hil/respond` 和 `/hil/ack_notification` 使用 Lua 原子状态转换；404/409 语义如上。 |
| D032 | HIL 状态 field 保存 `pending/responded/acked + expires_at`；过期不可回复。 |
| D033 | `expires_at` 是租约；`interrupt()` 心跳刷新租约和会话 Stream TTL；业务超时独立。 |
| D034 | 相关 TTL 3600s、心跳 60s；删除 `timeout_retry`，`timeout` 改为业务总超时。 |
| D035 | writer 对象隐藏、弱引用缓存、无串行锁、公共入口保持函数。 |
| D036 | writer 单次序列化，有限退避重试，错误向上抛出，at-least-once。 |
| D037 | writer 内按事件类型分派普通写入和 HIL 原子写入。 |
| D038 | `chat.reasoning_delta` 纳入 v1，payload 为 `{content: str}`；它表示 LLM 流式推理内容，当前没有独立 begin/end 事件。 |

## 7. 实施阶段计划（骨架）

> 详细计划待下一步编写；以下是阶段切分和验收边界。

| 阶段 | 目标 | 主要工件 | 初步验收 |
|---|---|---|---|
| P1 数据模型与契约 | 落地统一信封、payload 模型、事件 union 和排除项清理 | `api/chat/session_event_streaming/event_types.py`、新增公共事件模型模块 | 模型可序列化/反序列化；非法字段和 JSON 字符串 payload 被拒绝；事件目录测试通过 |
| P2 Writer 与状态基础设施 | 实现 writer、普通写入、HIL 原子写入、TTL 刷新 | writer 模块、Redis Lua、状态 Hash | 重试/异常传播/TTL/HIL pending 原子性测试通过 |
| P3 生产端接入 | Session/Chat/HIL 改为构造类型化事件并写入会话 Stream | Session publisher、`StreamingProcessor`、HIL context/interrupt/notification、`chat_task` 上下文传递 | 单会话多条事件可进入同一 Stream；HIL 下行/上行链路可用 |
| P4 会话 SSE 端点 | 实现单会话消费、鉴权、心跳、续读、游标过期注释、HIL 过滤 | 新 endpoint、SSE 工具 | 建连/断线续读/游标过期/HIL 已处理过滤/断开清理 |
| P5 客户端协议与集成验证 | 更新 SSE 规范和前端接入说明，跑跨任务端到端验证 | SSE 开发规范、协议文档、测试脚本 | 前端可只建一条连接完成多任务；注释帧可被识别；历史回拉可用 |
| P6 旧接口拆除 | 删除三个旧 SSE 路由、旧监听器、send_stream 残留和废弃事件 | 旧 endpoint/listener/publisher、HIL send_stream 相关代码 | 代码中无旧 SSE 路由和废弃类型；全量测试通过 |

## 8. 生产端接入待解问题

这些问题应在 P3 计划中逐项落定：

1. Session 事件从 Pub/Sub 改为 writer 的具体落点；
2. Chat `StreamingProcessor` 如何补齐 `session_id`、`branch_name` 并构造类型化事件；
3. HIL `interrupt()` / `notification()` 如何写入 HIL 事件并登记 `pending + expires_at`；
4. HIL 等待期间的心跳任务如何取得 writer/状态存储能力并管理生命周期；
5. `session_id` 从 `ToolFactory` / `chat_task` 向 HIL 调用链传递的路径。

## 9. 未决事项

- `Last-Event-ID` 首次缺失时的行为：从 0 开始、从 `$` 开始，还是返回空等待；
- SSE 游标过期注释的最终文本，以及客户端解析约定；
- 会话 Stream 的 `MAXLEN`/`MINID` 裁剪参数；
- HIL `expires_at` 的精确编码方式与过期 field 清理策略；
- `HILInterruptTimeout` 的最终命名和继承关系；
- at-least-once 重试导致重复事件时，是否需要逻辑事件 ID 或客户端去重；
- 新 SSE 路由路径、请求模型和 `init` 帧内容；
- `system` 信道是否需要在 v1 定义错误/诊断事件。

## 10. 权威指针与当前状态

### 10.1 实现与规范指针

| 内容 | 指针 |
|---|---|
| SSE 开发规范 | `docs/for_LLM_dev/SSE流式接口开发规范.md` |
| Chat SSE 与监听 | `api/app/chat/listen_to_session_streaming.py`、`api/chat/stream_listener.py` |
| Chat 事件生产 | `api/chat/streaming_processor.py` |
| Session SSE 与生产 | `api/app/chat/session_event_streaming/`、`api/chat/session_event_streaming/` |
| HIL SSE/生产/上下文 | `api/human_in_loop/http_worker/`、`api/human_in_loop/context.py`、`interrupt.py`、`notification.py` |
| 任务启动与主流程 | `api/app/chat/process_pending_messages.py`、`api/chat/chat_task.py` |
| SSE 心跳工具 | `api/sse_utils.py` |
| 工具工厂与 HIL 调用链 | `api/agent/tools/tool_factory/tool_factory.py`、`api/agent/tools/ask_user/constructor.py` |

### 10.2 历史背景（只留结论）

- Chat 旧模型以 `StreamingMessage.content: str` 为核心，早期面向 OpenAI 文本增量兼容；后来加入 tool/status 事件时用 `ujson.dumps()` 塞入字符串。
- HIL 旧实现是内部 Redis/WebSocket RPC 邮箱，使用 `pickle` 传递 Python 对象；JSON 化发生在读取侧而不是生产侧。
- Session 事件较晚引入，已经有结构化 Pydantic payload。

需要追溯时使用 git 历史即可，不在本档复述完整过程；关键提交：`25f3055`、`7ee838a`、`83efe3e`、`4d523a1`、`d1adb5f`、`2abe912`、`c08f1ee`。

### 10.3 当前基线

```text
git branch: fix/sse-protocol-consistency
HEAD:       ddb555b
worktree:   仅 docs/ai_paradigm/ 和 docs/handoff/ 未跟踪
代码状态:   未修改
```

## 11. 环境与复验

```bash
cd /home/gmh/桌面/IDIOT
git rev-parse --short HEAD
git status --short
grep -RIn 'prefix="/chat"\|prefix="/session_events"\|prefix="/hil"' api/app/chat api/human_in_loop
grep -RIn 'Last-Event-ID\|SSE_HEARTBEAT_FRAME\|stream_end' api/app/chat api/chat api/human_in_loop api/sse_utils.py
```

- 当前任务不需要启动服务或连接 Redis；设计阶段只做静态核对和文档维护。
- 仓库部分 `k8s/volumes/*` 权限有限，递归 grep/find 报权限错误不代表代码缺失。
- 本档是 handoff，不是最终协议规范；协议定稿后应建立权威协议文档并从本档链接。

## 12. 协作方式

- 文档范式：`docs/ai_paradigm/handoff_paradigm.md`。
- 项目通用纪律：`CLAUDE.md`。
- 当前任务纪律：**先完成阶段拆分和每阶段实现计划并确认，再开始修改 SSE 实现代码。**

## 13. 易忘备忘

- **下一步不是写代码，而是拆分阶段并为每个阶段写实现计划。**
- **一条连接只负责一个会话内的多个任务**；不跨 session 聚合。
- **单一会话 Stream、单一 `Last-Event-ID`**；请求体无游标且语义幂等。
- **`payload` 必须是 JSON 对象**；不要重新引入 `content: str` 套 JSON。
- **`chat.reasoning_delta` 已纳入 v1**：用于发送 LLM 推理/思考过程的流式增量，payload 为 `{content: str}`。
- **HIL send_stream 计划删除**：最终形态为下行会话 Stream、上行 recv_stream，`hil_interaction_state:{session_id}` 做软删除和并发控制；当前代码尚未改动。
- **HIL 业务超时与 Redis 租约分离**：心跳刷新租约；`timeout` 是内部单调时钟控制的业务总超时。
- **旧 SSE 接口最终删除**，但必须等新接口验证通过后再移除。
- **不要用全局 `stream_end` 结束会话连接**：任务/信道结束不等于连接结束。
- **客户端解析器必须识别 SSE 注释**，不能一律忽略 `:` 行。
- **MAXLEN/裁剪参数仍未定**：TTL 只限制空闲过期，不限制活跃 Stream 大小。
