---
name: sse-session-event-bus-implementation-plan
role: implementation-plan
status: confirmed
depends_on: docs/handoff/sse-session-event-bus.md
updated: 2026-11-04
---

# SSE 会话级事件总线实施计划

## 0. 使用前提

- 本文是**待确认计划**，不是实现结果。
- 在用户确认第 2 节的待裁项与第 5 节的阶段边界之前，不修改 SSE 实现代码。
- 确认后按 P1 → P6 顺序实施；每阶段结束必须先满足该阶段的验收条件，再进入下一阶段。
- 设计约束以 `docs/handoff/sse-session-event-bus.md` 的 D001–D038 为准；本文只补充落地细节。

## 1. 当前基线核对

核对命令：

```bash
cd /home/gmh/桌面/IDIOT
git rev-parse --short HEAD
git status --short
grep -RIn 'prefix="/chat"\|prefix="/session_events"\|prefix="/hil"' api/app/chat api/human_in_loop
```

2026-11-04 本计划编写时的实际状态：

- HEAD：`506ba76`（在 handoff 快照提交 `ddb555b` 之上增加了 handoff 文档提交）；
- 工作区干净；
- 三个旧 SSE 路由仍存在：
  - `api/app/chat/router_declare.py` 提供 `/chat`；
  - `api/app/chat/session_event_streaming/router_declare.py` 提供 `/session_events`；
  - `api/human_in_loop/http_worker/router.py` 提供 `/hil`；
- 当前 Session 事件仍是 Redis Pub/Sub；
- 当前 Chat 使用 `u2a_msg_stream:{session_task_id}`；
- 当前 HIL 使用 `human_in_loop_send_stream:{session_task_id}` 与 `human_in_loop_recv_stream:{session_task_id}`，并使用 pickle。

## 2. 待确认决策

以下决策闭合 handoff 第 9 节未决事项。建议全部按“建议”执行；若用户无异议，实施时视为冻结约束。

| ID | 问题 | 建议 | 影响 |
|---|---|---|---|
| Q01 | 首次连接没有 `Last-Event-ID` 时从哪里读 | `"0"`，回放保留窗口内的历史事件 | 新页面可看到连接建立前已发生的事件；客户端按 Redis ID 去重 |
| Q02 | 游标过期注释文本 | 固定为 `: cursor-expired\n\n`；心跳仍是 `: heartbeat\n\n` | 客户端必须区分两种注释，不能一律忽略 |
| Q03 | Stream 裁剪策略 | XADD 使用 `MAXLEN ~ 50000`，同时 TTL 3600 秒；常量集中配置 | 防止活跃会话无限增长；不承诺窗口外补发，符合 D002 |
| Q04 | HIL `expires_at` 编码与过期清理 | Hash value 为紧凑 JSON：`{"state":"pending","expires_at":<unix_ms>}`；Lua 内用 Redis `TIME` 生成和比较；过期时 HDEL；无后台清扫器 | 多实例不受本机时钟偏差影响；Hash key TTL 兜底 |
| Q05 | HIL 超时异常命名与继承 | `HILInterruptTimeout(HILInterruptCancelled)` | 新代码可精确区分；已有宽泛捕获仍兼容 |
| Q06 | 重试造成的重复事件 | **已选方案 A**：v1 接受 at-least-once，不增加逻辑事件 ID；Redis entry ID 仍是 SSE 唯一游标 | 文档标注极端情况下文本 delta 可能重复；后续版本再评估逻辑事件 ID |
| Q07 | 新 SSE 路由与请求体 | 使用 `POST /api/chat/session_streaming`（FastAPI 内部 `/chat/session_streaming`），请求体仅 `{session_id}`；init 仍为 `event:init data:{"status":"connected"}`；代码模块使用 `api/chat/session_streaming` 与 `api/app/chat/session_streaming` | 删除 `/chat/streaming`、`/hil/streaming` 与 `/session_events/streaming`；新路由不与旧路径并存 |
| Q08 | `system` 信道 v1 是否定义事件 | 仅保留名字，不定义任何 `system` 业务事件 | 不扩大 v1 范围；运行时错误只记日志并断开，由客户端重连 |
| Q09 | 重连时 HIL 历史事件过滤 | 对带 `msg_id` 的 HIL 交互事件读取状态 Hash；仅 `pending` 且未过期才下发；`hil.stream_end` 不过滤 | 已回复/已确认的旧表单不重复弹出 |
| Q10 | `/hil/respond`、`/hil/ack_notification` 如何得到 `session_id` | 服务端按 `session_task_id` 查任务，校验任务属于当前用户，并从任务取 `session_id`；请求体不新增字段 | 不改变前端上行请求格式，同时补上所有权校验 |
| Q11 | HIL 响应写入和状态转换是否原子 | 同一个 Lua 完成：校验 pending、改 responded、XADD recv_stream、刷新 TTL；recv_stream 取消 pickle，改 JSON | 避免“已标记 responded 但响应没写进 recv_stream”的中间态 |
| Q12 | `hil.stream_end` 谁发、何时发 | 每个 `session_chat_task` 的最终 `finally` 发一次，表示该任务的 HIL 信道结束 | 不关闭会话级 SSE；与 `chat.stream_end`、`session.branch_task_completed` 并列 |
| Q13 | 写事件失败是否影响核心任务 | 低层 `publish_session_stream_event()` 必须抛出；Chat/Session 生产端明确捕获并记录日志，保持 UI 推送 best-effort | 满足 D036 的 writer 契约，同时避免 Redis 短暂故障导致 Agent 任务失败 |
| Q14 | 旧 WebSocket HIL worker | 若确认仓库内无独立部署入口，P6 一并删除；否则必须先移植，不能保留依赖 send_stream 的半死代码 | 彻底满足“删除 HIL send_stream” |

## 3. 目标模块与契约

### 3.1 最终模块布局

```text
api/chat/session_streaming/
  events.py              # 统一信封、payload、discriminated union、TypeAdapter
  constants.py           # key 前缀、TTL、MAXLEN、心跳参数
  writer.py              # SessionStreamWriter + publish_session_stream_event()
  hil_state.py           # HIL 状态 Hash 的 Lua：发布 pending、刷新租约、状态转换、清理
  # 旧包 api/chat/session_event_streaming/ 在迁移期保留，P6 删除

api/app/chat/session_streaming/
  endpoint.py            # 唯一的会话级 SSE 端点
  listener.py            # 从 session_event_stream:{session_id} 读取并过滤

api/human_in_loop/
  data_model.py          # 从 interrupt.py/notification.py 抽出的中立领域模型
  interrupt.py           # 新 HIL interrupt：发布事件、等待 recv_stream、业务超时、租约心跳
  notification.py        # 新 HIL notification：发布会话事件并登记 pending
  interaction_service.py # /hil/respond 与 /hil/ack_notification 的领域服务
  # context.py / http_worker/stream_listener.py / long_poll_worker.py 等旧路径 P6 删除
```

说明：新增 `events.py` 而不是立刻覆盖旧 `event_types.py`，目的是让 P1/P2 期间旧生产端仍可 import，避免阶段中间态整体不可运行。P3 完成生产端迁移后，P6 删除旧文件。

### 3.2 统一事件契约

```python
SessionStreamEvent = Annotated[
    Annotated[SessionChannelEvent, Field(discriminator="type")]
    | Annotated[ChatChannelEvent, Field(discriminator="type")]
    | Annotated[HilChannelEvent, Field(discriminator="type")],
    Field(discriminator="channel"),
]
SessionStreamEventAdapter = TypeAdapter(SessionStreamEvent)
```

信封固定字段：

```text
v: Literal[1] = 1
channel: session | chat | hil          # system 保留但 v1 无事件
type: 对应事件类型
session_id: UUID
session_task_id: UUID                  # v1 所有业务事件必填
branch_name: str | None
payload: 事件专属 Pydantic 模型
```

约束：

- 信封、每个 payload、以及 HIL 领域模型均 `extra="forbid"`；
- 每个空 payload 使用独立类；
- 内部只传 Pydantic 对象；
- writer 边界只调用一次 `event.model_dump_json()`；
- 消费端只调用一次 `SessionStreamEventAdapter.validate_json()`；
- SSE `event` 名为 `f"{event.channel}.{event.type}"`；
- SSE `id` 只用 Redis Stream entry ID，事件体内不写 entry ID。

事件目录：

| channel | type | payload |
|---|---|---|
| session | `branch_task_started` | `{}` |
| session | `branch_task_completed` | `{outcome, has_exception}` |
| chat | `text_msg_begin` | `{}` |
| chat | `text_msg_delta` | `{content}` |
| chat | `text_msg_end` | `{}` |
| chat | `reasoning_delta` | `{content}` |
| chat | `tool_call` | `{tool_exec_uuid, tool_name}` |
| chat | `tool_response` | `{tool_exec_uuid, tool_result}` |
| chat | `stream_end` | `{outcome, error}` |
| hil | `HIL_interrupt_request` | `{msg_id, content}` |
| hil | `Notification` | `{msg_id, content}` |
| hil | `stream_end` | `{}` |

`outcome` 取 `completed | cancelled | failed`。`chat.stream_end.error` 为 `str | None`。`tool_result` v1 建议为 `dict[str, Any] | None`，与当前 `ToolTaskResult.model_dump(mode="json")` 对齐。

### 3.3 Redis 键与常量

```text
session_event_stream:{session_id}
hil_interaction_state:{session_id}
human_in_loop_recv_stream:{session_task_id}

SESSION_EVENT_STREAM_TTL_SECONDS      = 3600
SESSION_EVENT_STREAM_MAXLEN           = 50000
HIL_INTERACTION_STATE_TTL_SECONDS     = 3600
HIL_INTERACTION_LEASE_MS              = 3600_000
HIL_LEASE_HEARTBEAT_SECONDS           = 60
HIL_INTERRUPT_DEFAULT_TIMEOUT_SECONDS = 3600
SSE_HEARTBEAT_SECONDS                 = 15
```

### 3.4 Writer 公共接口

```python
async def publish_session_stream_event(event: SessionStreamEvent) -> str:
    """写入 event.session_id 对应的会话 Stream，返回 Redis entry ID。"""

async def refresh_session_stream_ttl(session_id: UUID) -> None:
    """内部/心跳使用：刷新会话 Stream TTL，不要求 Stream 已存在。"""
```

实现要点：

- 模块级 `WeakValueDictionary[UUID, SessionStreamWriter]`，按 `event.session_id` 懒加载；
- 公共函数调用期间持有 writer 强引用；
- 不创建常驻后台任务，不加 per-session 串行锁；
- 序列化在重试闭包外执行一次；
- `ConnectionError` 与 `TimeoutError` 重试，初始 + 3 次重试，退避 0.5s/1s/2s；
- Pydantic 校验错误、`DataError`、其他 `ResponseError` 不重试；
- 普通事件使用 `MULTI`：`XADD ... MAXLEN ~ 50000 * event <json>` + `EXPIRE 3600`；
- HIL 交互事件使用 Lua：XADD、HSET pending + expires_at、两个 EXPIRE 原子完成；
- `hil.stream_end` 按普通事件写入，不登记状态；
- 出现重试歧义时可能重复写入，这是 v1 已知语义。

### 3.5 HIL 状态与响应

Hash field：

```text
hil_interaction_state:{session_id}
  HIL msg_id -> '{"state":"pending","expires_at":1760000000000}'
```

状态转换：

- `/hil/respond`：`pending -> responded`，并在同一个 Lua 中向 `human_in_loop_recv_stream:{session_task_id}` XADD JSON 响应；
- `/hil/ack_notification`：`pending -> acked`；
- 字段不存在或已过期：HTTP 404；
- 字段状态不是 `pending`：HTTP 409；
- 用户无任务所有权：HTTP 404；
- 同一 Lua 刷新状态 Hash 与 recv_stream 的 TTL。

recv_stream entry 建议仅保留一个字段 `event`：

```json
{"msg_id":"<uuid>","content":"用户响应或结构化对象"}
```

这样 `interrupt()` 只需一次 JSON 反序列化，与下行 JSON 化方向一致，彻底移除 pickle。

### 3.6 HIL interrupt 等待流程

```text
生成 msg_id
  -> 构造 HilInterruptRequestEvent
  -> publish_session_stream_event()（原子登记 pending）
  -> 启动 60 秒租约心跳任务
  -> 循环 XREAD human_in_loop_recv_stream:{session_task_id}
       - 解析 event JSON
       - 跳过其他 msg_id
       - 匹配则 XDEL 并返回 content
       - 检查 cancel_event
       - 用 monotonic deadline 检查业务总超时
  -> finally 停止心跳
       - 正常响应：无需删除状态（保持 responded 供重连过滤）
       - 超时：best-effort HDEL pending，抛 HILInterruptTimeout
       - 取消：best-effort HDEL pending，抛 HILInterruptCancelled
```

心跳任务每 60 秒执行一次 Lua，仅当状态仍为 pending 时刷新：

- 当前 field 的 `expires_at`；
- `hil_interaction_state:{session_id}` TTL；
- `session_event_stream:{session_id}` TTL。

Redis 租约只做故障兜底；业务总超时只由 `time.monotonic()` 决定。

### 3.7 “at-least-once、不增加逻辑事件 ID”是什么意思

先区分两种 ID：

- **Redis Stream entry ID**：由 Redis `XADD` 生成，例如 `1760000000000-0`。它是 SSE 的 `id`，也是 `Last-Event-ID` 的游标。
- **逻辑事件 ID**：业务层为“同一个事件”生成的稳定 UUID。它不随 Redis 重试变化。

at-least-once 的执行过程示例：

```text
1. 生产端要发一条 chat.text_msg_delta；
2. Redis 实际已执行 XADD 成功；
3. 网络在返回结果前断开，writer 收到 ConnectionError；
4. writer 按 D036 重试；
5. Redis 再次执行 XADD 成功。
```

结果：同一个逻辑 delta 在 Stream 中有两个 entry，具有两个不同的 Redis entry ID。SSE 客户端会看到两次。

“不增加逻辑事件 ID”的含义是：

- 事件体里没有稳定 UUID 用来识别“这两条其实是同一条”；
- 客户端只能看到两个不同的 SSE `id`，无法通用地去重；
- HIL 可以用 payload 里的 `msg_id` 去重，工具事件可以用 `tool_exec_uuid` 部分去重，但普通文本 delta 没有现成稳定键。

两个可选方案：

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A（当前暂定） | 只保证 at-least-once，不加字段；文档标注文本重复风险 | 契约最简单，不增加客户端状态 | 极端网络故障下文本 delta 可能重复显示 |
| B（建议评估） | 信封增加 `event_id: UUID`，由生产端构造事件时生成；writer 重试复用同一 JSON；客户端按 `event_id` 去重 | 所有事件可通用去重；SSE `id` 仍用 Redis entry ID，不影响续读 | 多一个契约字段和客户端最近事件 ID 缓存 |

**最终选择：方案 A。** v1 不增加 `event_id`，接受 at-least-once 的重复风险，不为此引入额外契约和客户端复杂度。

## 4. 阶段总览

| 阶段 | 目标 | 依赖 | 退出标志 |
|---|---|---|---|
| P1 数据模型与契约 | 新统一模型可构造、序列化、反序列化、拒绝非法输入 | 无 | 模型测试通过；旧生产端仍可 import |
| P2 Writer 与 HIL 状态基础设施 | 普通/HIL 原子写入、重试、TTL、状态转换可用 | P1 | writer/状态单元测试通过；Redis 集成脚本通过 |
| P3 生产端接入 | Session/Chat/HIL 全部只写新会话 Stream | P1/P2 | 单会话多任务事件写入同一 Stream；HIL 中断上行可用 |
| P4 会话 SSE 端点 | 单连接消费、鉴权、心跳、续读、过期注释、HIL 过滤 | P2/P3 | 直连 Redis + HTTP 流验证通过 |
| P5 客户端协议与集成验证 | 协议文档、前端接入约定、跨任务端到端验证 | P4 | 一次连接覆盖多任务；断线续读可验证 |
| P6 旧接口拆除 | 删除三个旧 SSE、旧 listener/publisher/send_stream 残留 | P5 | grep 无旧入口和废弃事件；全量测试通过 |

## 5. 分阶段实施计划

### P1 数据模型与契约

**目标**

- 落地统一信封、所有 payload、按 channel/type 的嵌套 discriminated union；
- 抽出 HIL 领域模型，解除未来的循环依赖；
- 不触碰生产端行为，保证阶段中间态仍可 import。

**工件**

- 新增 `api/chat/session_streaming/events.py`；
- 新增 `api/chat/session_streaming/constants.py`；
- 新增 `api/human_in_loop/data_model.py`；
- 修改 `api/human_in_loop/interrupt.py`、`notification.py`，改为从新模块导入并 re-export；
- 新增 `tests/session_streaming/test_event_models.py`。

**任务**

1. 将 `HILInterruptContent*`、`HILNotificationContent*` 移至中立模块，保持旧 import 路径兼容；为它们加 `extra="forbid"`。
2. 定义公共信封基类与各事件具体类，事件名与第 3.2 节目录一致。
3. 为每个空 payload 建独立类；所有模型设置 `extra="forbid"`。
4. 定义 `SessionChannelEvent`、`ChatChannelEvent`、`HilChannelEvent` 三个按 `type` 的 union，再定义按 `channel` 的顶层 union 与 `TypeAdapter`。
5. 删除新模型中的 `mem_*`、`status_*`；旧 `event_types.py` 暂不删除。
6. 固化 `outcome`、`tool_result`、`branch_name` 等字段类型。

**约束**

- D014–D028、D038；
- `payload` 必须为对象；禁止 JSON 字符串套 JSON；
- HIL payload 复用领域模型，不复制字段定义；
- Redis entry ID 不进入事件模型。

**验证**

```bash
.venv/bin/python -m pytest tests/session_streaming/test_event_models.py
```

测试覆盖：

- 12 个事件类型逐一构造、`model_dump_json()`、`validate_json()` 后类型与 payload 等价；
- 顶层 union 按 channel、内层 union 按 type 正确分派；
- 信封和 payload 的多余字段均被拒绝；
- payload 传 JSON 字符串、数组、null 均被拒绝；
- 旧 `status_*` / `mem_*` 类型不在新 union 中；
- `chat.reasoning_delta` 存在且 payload 为 `{content: str}`。

**阶段结束可观察状态**

- 新模型可在不启动服务、不连接 Redis 的情况下完整测试；
- 旧生产代码不受影响。

**下一步依赖**

- P2 只依赖 `events.py` 和 `constants.py`，不依赖生产端迁移。

---

### P2 Writer 与 HIL 状态基础设施

**目标**

- 实现唯一写入入口、普通事件原子写、HIL 事件与 pending 状态原子写、TTL 刷新、有限重试；
- 实现 HIL 状态转换 Lua，供后续生产端与 HTTP 上行复用。

**工件**

- 新增 `api/chat/session_streaming/writer.py`；
- 新增 `api/chat/session_streaming/hil_state.py`；
- 修改 `api/redis/retry.py`：重试异常集合增加 `redis.exceptions.TimeoutError`（保持现有调用兼容）；
- 新增 `tests/session_streaming/test_writer.py`；
- 新增 `tests/session_streaming/test_hil_state.py`；
- 新增可选集成测试 `tests/integration/test_session_event_redis.py`（无 Redis 时 skip）。

**Writer 任务**

1. 实现 `SessionStreamWriter`：持有 `session_id`，无后台任务；`WeakValueDictionary` 懒加载。
2. 普通事件路径：单次序列化，`MULTI` pipeline 执行 XADD + EXPIRE。
3. HIL 交互事件路径：调用 `hil_state` 的原子发布脚本；按 `event.type` 分派，不让调用方判断。
4. 实现重试：仅 `ConnectionError`、`TimeoutError`；退避 0.5/1/2 秒；其他异常原样抛出。
5. 实现 `refresh_session_stream_ttl(session_id)` 供心跳调用。
6. 返回并规范化 Redis entry ID 为 `str`。

**HIL 状态任务**

1. `publish_pending_interaction_event(session_id, msg_id, event_json) -> stream_id`：
   - XADD event + MAXLEN；
   - HSET field 为 pending JSON；
   - EXPIRE stream 与 state hash。
2. `refresh_pending_lease(session_id, msg_id) -> bool`：
   - 仅 pending 时更新 `expires_at`、两个 TTL；
   - 状态不存在或非 pending 返回 false。
3. `transition_to_responded(session_id, session_task_id, msg_id, response_json) -> TransitionResult`：
   - 校验存在、过期、pending；
   - 改状态为 responded；
   - XADD recv_stream JSON；
   - 刷新 recv_stream 与状态 TTL；
   - 返回 success/not_found/conflict。
4. `transition_to_acked(session_id, msg_id) -> TransitionResult`：同上但不写 recv_stream。
5. `discard_pending(session_id, msg_id)`：仅 best-effort 删除 pending 字段。
6. 所有时间比较使用 Lua 内 Redis `TIME`。

**约束**

- D008、D030–D037；
- writer 不暴露具体 Redis 命令给生产端；
- 状态转换必须单 Lua；
- 不重试确定性响应错误；
- 不引入后台清扫任务。

**验证**

单元测试（mock Redis）：

- 普通写入命令顺序为带 MAXLEN 的 XADD + EXPIRE，且同一 pipeline；
- 序列化只发生一次；
- `ConnectionError`/`TimeoutError` 按指定退避重试；
- `DataError`/`ResponseError` 不重试且上抛；
- HIL 事件走 EVAL，`hil.stream_end` 走普通 XADD；
- 返回 entry ID 为 str。

Redis 集成测试（需要 disposable Redis）：

- XADD 后 Stream 同时存在且 TTL > 0；
- HIL 发布后 field 状态为 pending、expires_at 合理；
- 已过期/不存在返回 not_found；
- 连续两次 respond：第一次成功、第二次 conflict；
- respond 成功时 recv_stream 同步出现一条响应，状态为 responded；
- ack 后状态为 acked；
- 心跳刷新 field 的 expires_at 与两个 key TTL；
- Lua 执行失败/连接中断时错误不被吞掉。

**阶段结束可观察状态**

- 可用一个独立脚本向任意 `session_id` 写入合法事件并按原始 Redis 命令核验；
- 可用独立脚本完成 HIL pending → responded/acked 状态转换；
- 生产端仍未切换，旧功能不受影响。

**下一步依赖**

- P3 的所有生产端只依赖 `publish_session_stream_event()` 与 HIL 状态接口。

---

### P3 生产端接入

**目标**

- Session、Chat、HIL 下行全部改为构造类型化事件并写同一个会话 Stream；
- HIL 上行改为 `/hil/respond` + Lua 状态转换 + recv_stream；
- 移除 Session 记忆事件和 Chat 状态事件的生产调用。

**工件**

- 修改 `api/chat/streaming_processor.py`；
- 修改 `api/chat/chat_task.py`；
- 修改 `api/agent/strategy/main_agent_strategy.py`（删除 mem 事件）；
- 修改 `api/agent/strategy/main_agent.py`（如构造参数变化）；
- 修改 `api/agent/tools/ask_user/constructor.py`；
- 修改 `api/agent/tools/tool_factory/tool_factory.py`（如存在参数透传缺口）；
- 重写 `api/human_in_loop/interrupt.py`、`notification.py`；
- 新增 `api/human_in_loop/interaction_service.py`；
- 修改 `api/human_in_loop/http_worker/router.py` 的 respond/ack 实现；
- 新增 `tests/session_streaming/test_producers.py`、`tests/human_in_loop/test_interrupt.py`。

**Chat 生产端任务**

1. `StreamingProcessor` 构造参数改为 `session_id`、`session_task_id`、`branch_name`。
2. 每个 `push_*` 方法构造对应 chat 事件：
   - `push_text_start_msg` → `chat.text_msg_begin`；
   - `push_text_delta_msg` → `chat.text_msg_delta`；
   - `push_text_end_msg` → `chat.text_msg_end`；
   - `push_reasoning_delta_msg` → `chat.reasoning_delta`；
   - tool call/response 使用结构化 payload；
   - `push_ending_message`/`push_exception_ending_message` 合并为显式 `push_stream_end(outcome, error)`。
3. 删除 `status_*` 方法、`StreamingMessage.content: str`、`_stream_key`、`TTL_deamon`。
4. Chat 事件写入失败时由 processor 捕获并记录，避免 UI 故障影响 Agent；但直接调用 writer 的测试断言错误会上抛。
5. 在 `session_chat_task` 的统一 `finally` 中只发一次 `chat.stream_end`，记录最终 outcome：
   - 正常 → completed；
   - `SessionChatTaskCancelled` → cancelled；
   - 未处理异常 → failed；
   - 其他取消路径也要映射为 cancelled。

**Session 生产端任务**

1. `branch_task_started`：branch_name、session_task_id 放信封，payload 为空。
2. `branch_task_completed`：同一 finally 发一次；payload 为 `{outcome, has_exception}`。
3. 删除 `main_agent_strategy` 中全部 `mem_recall_*` / `mem_write_*` 发布调用和 import。
4. `publish_SSE_session_event` 调用点全部切换为 `publish_session_stream_event`。
5. 生命周期事件推送失败 best-effort：记录日志但不改变任务 DB 终态。

**HIL 生产端任务**

1. 将 `HILInterruptContent` 与 `HILNotificationContent` 作为 HIL 事件 payload 的 `content` 字段。
2. `interrupt()` 新签名至少包含：
   ```python
   async def interrupt(
       content: HILInterruptContent,
       *,
       session_id: UUID,
       session_task_id: UUID,
       branch_name: str | None = None,
       timeout: float = 3600,
       cancel_event: Event | None = None,
   ) -> str | dict | None
   ```
   删除 `stream_identifier`、`timeout_retry`。
3. 生成 msg_id → 发布 `hil.HIL_interrupt_request` → 等待 recv_stream。
4. `notification()` 同样接收 session 上下文，发布 `hil.Notification`，返回 msg_id（如有需要）。
5. AskUserChoice 构造时从 ToolFactory 传入 `session_id`、`session_task_id`、`branch_name`；不要靠 kwargs 中偶然出现的 metadata。
6. chat_task 在最终 finally 发 `hil.stream_end`，然后由 P6 删除 `HILMessageStreamContext`。
7. `/hil/respond` 和 `/hil/ack_notification`：
   - 先按 session_task_id 查任务并校验当前用户；
   - 用任务 session_id 调 `interaction_service`；
   - 状态层 not_found → 404，conflict → 409；
   - 不再读写 send_stream，不使用 pickle。
8. 删除 `timeout_retry` 参数与旧循环重发语义；`timeout` 只表示业务总超时。
9. 新增 `HILInterruptTimeout(HILInterruptCancelled)`。

**约束**

- D003–D005、D008、D017、D019–D027、D030–D034、D038；
- 一条连接只对应一个 session；生产端只按 session_id 写；
- 任务/信道结束事件不终止 SSE 连接；
- 不存在 HIL 双写。

**验证**

```bash
.venv/bin/python -m pytest \
  tests/session_streaming/test_producers.py \
  tests/human_in_loop/test_interrupt.py
```

测试覆盖：

- 12 类 Chat/Session 事件经 processor 生成后，信封字段和 payload 完全正确；
- 同一任务的事件按调用顺序进入同一 `session_event_stream:{session_id}`；
- 删除 mem/status 生产调用后无残留 import；
- session_chat_task 正常/取消/异常三条路径各只发一次 chat.stream_end，outcome 正确；
- HIL interrupt 发布后状态为 pending，收到匹配响应后返回并消费 recv entry；
- 响应 msg_id 不匹配时跳过；
- 超时抛 `HILInterruptTimeout` 且 best-effort 清 pending；
- cancel_event 触发抛 `HILInterruptCancelled`；
- 心跳按 60 秒刷新 lease（测试用可注入间隔，不需要真等 60 秒）；
- respond/ack 的 404/409 与原子 recv 写入由集成测试覆盖。

**阶段结束可观察状态**

- 新事件只进会话级 Stream，不再进 `u2a_msg_stream` 或 HIL send_stream；
- 一个 session 的多个 task 事件可按 `session_task_id` 解复用；
- HIL 下行和上行链路在 Redis 层已闭环；
- 旧 SSE 端点仍存在但预期不再收到新事件。

**下一步依赖**

- P4 消费端只依赖 `session_event_stream:{session_id}`、事件模型和 HIL 状态 Hash。

---

### P4 会话 SSE 端点

**目标**

- 新增 `POST /chat/session_streaming`（外部 `/api/chat/session_streaming`）作为唯一会话级 SSE；
- 实现鉴权、心跳、`Last-Event-ID` 续读、游标过期注释、HIL 已处理过滤；
- 连接跨多个任务持续存在，任何 `stream_end` 都不关闭连接。

**工件**

- 重写 `api/app/chat/session_streaming/endpoint.py`；
- 重写 `api/app/chat/session_streaming/listener.py`；
- 必要时在 `api/sse_utils.py` 增加 `SSE_CURSOR_EXPIRED_FRAME` 或控制帧工具；
- 新增 `tests/session_streaming/test_endpoint.py`。

**任务**

1. 请求模型只保留 `session_id`；端点在建连前校验会话存在且属于当前用户。
2. 发送固定 init 帧。
3. 从 `Last-Event-ID` 解析游标：
   - 缺失 → `"0"`；
   - 合法格式为 `0` 或 `ms-seq`；
   - 非法 → HTTP 400，不建立长连接。
4. 监听器 XREAD `session_event_stream:{session_id}`：
   - 读取后保持游标不变直到下一轮；
   - 连接错误指数退避，游标不重置；
   - 不使用“连续空读上限”结束无限订阅；
   - 任何业务 `stream_end` 都只作为普通事件下发，不退出。
5. 游标过期检测：
   - Stream 存在时用 XRANGE 取最早 entry；
   - 请求游标严格早于最早 entry，且不是初始 `0` 时，先发 `: cursor-expired\n\n`；
   - 之后从当前可读最早事件继续。
6. 消费端反序列化事件；非法/旧格式 entry 记 warning 后跳过，不中断连接。
7. HIL 过滤：
   - 对 `HIL_interrupt_request` 与 `Notification` 读取 `hil_interaction_state`；
   - 字段不存在、已过期或状态非 pending 时跳过；
   - `hil.stream_end` 正常下发。
8. SSE 格式化：
   ```text
   event:{channel}.{type}
   data:{原始事件 JSON}
   id:{redis_entry_id}

   ```
9. 心跳由 `iter_with_heartbeat` 每 15 秒产生 `: heartbeat\n\n`；心跳不消耗 id。
10. generator 的 finally 正常清理 XREAD/任务，不向客户端补发全局结束事件。

**约束**

- D001–D017、D030–D034；
- 单个信道故障不关闭连接；
- 请求体无游标，重连语义幂等；
- 游标过期注释必须可被客户端识别。

**验证**

- 端点层：会话不存在/非本人 → 404；缺少鉴权 → 401；非法 Last-Event-ID → 400。
- 协议层：init 帧、业务帧 event/data/id、心跳帧、cursor-expired 帧精确匹配。
- 监听器：初始无 Stream 时等待；写入后收到；多个 task 事件顺序正确；收到各 channel `stream_end` 后继续读取后续新事件。
- 续读：从中间 ID 重连只得到之后事件；从早于最早 ID 重连先收到 cursor-expired 再收到当前窗口最早事件；Redis 闪断后游标不丢。
- HIL 过滤：pending 事件下发；responded/acked/expired 事件跳过；stream_end 下发。
- 客户端断开后 Redis 读循环结束。

**阶段结束可观察状态**

- 前端只建一条 `POST /api/chat/session_streaming`，即可看到 session/chat/hil 三类事件；
- 断线重连只依赖一个 `Last-Event-ID`；
- 已处理 HIL 表单不会在历史回放中重现。

**下一步依赖**

- P5 使用 P4 端点做跨任务端到端验证，并据此写权威协议文档。

---

### P5 客户端协议与集成验证

**目标**

- 将新协议写成唯一权威文档；
- 更新项目 SSE 开发规范，去掉 Pub/Sub 会话流与旧三接口的过时描述；
- 完成跨任务、断线续读、HIL 过滤的端到端验证。

**工件**

- 重写 `docs/api/session_streaming.apib` 为会话级总线协议；
- 更新 `docs/for_LLM_dev/SSE流式接口开发规范.md`；
- 更新 `docs/api/sessions.apib`、`docs/api/hil/index.apib` 中旧 SSE 入口说明（P6 完成删除）；
- 更新 `api/CONTEXT.md` 中三个旧事件流定义；
- 新增 `tests/integration/test_session_event_stream_e2e.py` 或可复验脚本；
- 可选：`docs/handoff/` 中刷新当前状态。

**协议文档必须写清**

1. 一个 session 一条连接，多 task 复用；
2. 请求体、鉴权、`Last-Event-ID` 缺失/合法/非法行为；
3. init、heartbeat、cursor-expired 三类控制帧；
4. 统一信封与 12 类事件 payload；
5. SSE event 名 `channel.type`；
6. 任务结束事件不等于连接结束；
7. at-least-once 与潜在重复；
8. HIL 已处理过滤语义；
9. 客户端必须解析注释行，不能无条件忽略；
10. 游标过期后只能从当前可读窗口继续，不承诺无限补发。

**集成验证场景**

1. 新会话先建 SSE，再发送两条消息触发两个 task：
   - 收到两个 `session.branch_task_started/completed`；
   - 所有 chat 事件带正确 task id；
   - 连接在第一个 task 结束后仍能接收第二个 task。
2. 在 chat delta 中途断开，用最后收到的 id 重连；
   - 无丢失（保留窗口内）；
   - id 单调；
   - 不重复收到已经确认的同一 entry。
3. 用早于 Stream 最早 entry 的 id 重连；
   - 收到 `: cursor-expired`；
   - 随后从最早可读事件继续。
4. HIL interrupt：
   - 前端收到 pending 表单；
   - 调用 respond 后重连，旧表单被过滤；
   - ack_notification 后同样过滤；
   - 过期表单 respond 返回 404。
5. 服务端发送 `chat.stream_end`/`hil.stream_end` 后客户端连接仍存活，新任务继续到达。

**约束**

- 文档中的示例必须是新信封，不能再出现 `event_type`、`content:str` 套 JSON；
- 注释帧语义必须与端点实现逐字一致；
- 不承诺跨 session 聚合。

**阶段结束可观察状态**

- 一个具备自定义 fetch SSE 客户端的调用方可仅凭文档完成接入；
- 前端不再依赖 task 级 SSE 路由；
- 端到端脚本可重复跑通上述场景。

**下一步依赖**

- P6 只有在 P5 全部通过后才删除旧实现。

---

### P6 旧接口拆除

**目标**

- 删除三个旧 SSE 路由与所有旧 SSE/send_stream 残留，只保留新的 `/chat/session_streaming`；
- 保证代码库无废弃的事件类型、监听器和 Redis key 引用；
- 全量测试通过。

**删除清单**

1. `POST /chat/streaming`：
   - `api/app/chat/listen_to_session_streaming.py`；
   - `ChatStreamingRequset`；
   - `api/chat/stream_listener.py`；
   - 旧 `u2a_msg_stream` 相关残留。
2. `POST /hil/streaming`：
   - `api/human_in_loop/http_worker/stream_listener.py`；
   - `HILStreamingRequest` 与路由 handler；
   - `HILMessageStreamContext`（若 P3 已停止使用）；
   - `human_in_loop_send_stream` 常量与所有引用。
3. `POST /session_events/streaming`：
   - 旧 `api/app/chat/session_event_streaming/` 整个包；
   - 从 `api/app/main.py` 移除旧 router import/include；
   - 旧 Pub/Sub listener 与 Redis channel。
4. 旧生产/发布：
   - 旧包 `api/chat/session_event_streaming/`（含旧 `event_types.py`、`publisher.py`）；
   - `publish_SSE_session_event`；
   - `PubChannelNames.session_events`；
   - `api/redis/human_in_loop.py` 中不再使用的 `HIL_RedisMsg` / `HIL_xadd_msg_with_expired`（若全仓无引用）。
5. 旧 HIL worker：
   - `api/human_in_loop/http_worker/long_poll_worker.py` 若已被 `interaction_service.py` 取代；
   - `api/human_in_loop/ws_worker/` 按 Q14 的确认结果删除或完成迁移；
   - 任何 `pickle`、`send_stream`、`long_poll` 残留。
6. 文档：
   - 从 `sessions.apib` 删除 `/chat/streaming`；
   - 从 `hil/index.apib` 删除 `/hil/streaming` 与长轮询旧说明；
   - 从旧文档删除 `/session_events/streaming`，以 `docs/api/session_streaming.apib` 为唯一协议；
   - 更新 `CONTEXT.md` 为“一条会话级事件流”。

**验收 grep**

```bash
grep -RIn 'prefix="/chat"\|prefix="/session_events"\|prefix="/hil"' api/app/chat api/human_in_loop
grep -RIn 'publish_SSE_session_event\|u2a_msg_stream\|human_in_loop_send_stream\|HIL_RedisMsg\|timeout_retry' api
grep -RIn 'status_begin\|status_update\|status_end\|mem_recall_\|mem_write_' api
grep -RIn 'event_type' api/chat/session_streaming api/app/chat/session_streaming
```

预期：

- `/chat/session_streaming` 存在且指向新端点；
- `/chat/streaming`、`/hil/streaming` 与 `/session_events/streaming` 均不存在；
- 上述废弃符号无命中；
- 全量测试通过。

## 6. 总体测试与验收命令

建议使用当前仓库的 `.venv`（实际环境下 `uv run` 可能受只读缓存影响）：

```bash
.venv/bin/python -m pytest tests/session_streaming -q
.venv/bin/python -m pytest tests/human_in_loop -q
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api
```

Redis 集成测试：

```bash
SESSION_EVENT_TEST_REDIS_URL=redis://127.0.0.1:6379/15 \
  .venv/bin/python -m pytest tests/integration/test_session_event_redis.py -q
```

若测试环境没有 Redis，P2 不能只靠 mock 验收 HIL Lua；必须使用 disposable Redis 跑一次状态转换脚本。

手动 grep 作为 P6 最终门禁：

```bash
grep -RIn 'publish_SSE_session_event\|u2a_msg_stream\|human_in_loop_send_stream' api || true
grep -RIn 'event:branch_task_started\|event:text_msg_delta\|event:HIL_interrupt_request' docs || true
```

## 7. 风险与已知限制

| 风险 | 处理 |
|---|---|
| at-least-once 重试产生重复事件 | v1 文档明确；客户端对 HIL 用 msg_id 去重，文本 delta 重复接受为已知风险 |
| Redis Pipeline/EVAL 网络歧义 | 与上同；不引入逻辑 ID，避免超出已确认契约 |
| Stream MAXLEN 裁剪导致游标过期 | `: cursor-expired` 注释 + 从当前窗口继续；不承诺无限补发 |
| HIL 心跳与响应并发 | 全部状态转换用 Lua；responded/acked 后心跳自动停止刷新 |
| SSE 连接长时间空闲后 Stream 过期 | 连接可继续等待；下一事件创建新 Stream，客户端可能收到 cursor-expired |
| 旧实现删除后无兼容层 | D008 已允许；P5 验收后再删，不做双轨长期维护 |
| 当前仓库缺少 SSE 测试基础 | 每阶段新增最小测试；P2 起补 Redis 集成测试 |

## 8. 实施前确认清单

请确认以下事项后才开始 P1 编码：

- [ ] 接受第 2 节 Q01–Q14 的建议，或指出需要修改的条目；
- [ ] 接受 P1–P6 的阶段拆分与依赖顺序；
- [ ] 接受新增 `events.py`、`writer.py`、`hil_state.py`、`interaction_service.py` 的模块边界；
- [ ] 接受 `POST /api/chat/session_streaming` 作为唯一 SSE 路由，并使用 `api/chat/session_streaming` / `api/app/chat/session_streaming` 模块路径；
- [ ] 接受 `MAXLEN ~ 50000` 作为初版裁剪参数；
- [x] 已选择 Q06 方案 A：接受 at-least-once、不加逻辑事件 ID；
- [ ] 确认旧 HIL WebSocket worker 是否在 P6 删除。
