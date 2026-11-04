# SSE 流式接口开发规范

## 项目约定：POST + 自定义 fetch 客户端

项目中的 SSE 接口统一使用 `POST` + JSON 请求体建立连接，并通过 Bearer Token 鉴权。该方案无法使用浏览器原生 `EventSource`，因此客户端使用 `fetch` + `ReadableStream` 手动解析 SSE 帧。

这意味着以下职责由客户端自行实现：

- 解析 `event`、`data`、`id`、`retry` 字段；
- 解析以 `:` 开头的注释行，并区分 `heartbeat` 与 `cursor-expired`；
- 记录最后收到的业务事件 `id`；
- 重连时重新发送 POST，并手动携带 `Last-Event-ID`；
- 根据应用协议决定何时重连，不能只根据连接 EOF 推断业务结束。

当前项目唯一的会话级 SSE 路由是：

```
POST /api/chat/session_streaming
FastAPI 内部路径：/chat/session_streaming
```

请求体只包含 `session_id`。Session、Chat、HIL 三类事件共用这一条连接；不再按 `session_task_id` 建立独立 SSE。

## 为什么是 Redis Stream + SSE

SSE 是单向的持久 HTTP 连接，服务器可以持续推送消息。它比 WebSocket 轻量（纯 HTTP），比轮询高效（长连接）。

SSE 本身不解决“消息从哪来”的问题。选择 Redis Stream 作为消息管道是因为：

- **消息有序且有 ID** — 每条消息自带 Redis entry ID，天然支持“从某个位置之后继续读”；
- **生产消费解耦** — 生产者写完即走，消费者随时接入；
- **可持久化** — 保留窗口内的事件不会因连接短暂断开而丢失，客户端可续读。

Redis Stream 使用 `XADD ... MAXLEN ~ 50000` 裁剪，并设置 3600 秒 TTL。只保证保留窗口内的一定程度续读，不承诺无限期补发。

## 最终数据流

```
Session 事件 ─┐
Chat 事件    ├──> session_event_stream:{session_id} ──> 一条 SSE ──> 前端
HIL 事件     ┘
```

- 一条连接只负责一个 `session_id`，不跨会话聚合；
- 连接跨该会话的多个 `session_task_id` 持续存在；
- Redis Stream entry ID 同时作为 SSE `id` 和 `Last-Event-ID`；
- 请求体不携带游标，相同请求体表示恢复同一条逻辑订阅；
- 任务结束只发送任务级/信道级结束事件，不关闭会话连接。

## 三个关注点

实现一个 SSE 接口，本质上是处理三个独立的问题：

```
1. 谁能读？      → 端点层的鉴权与校验
2. 从哪读？      → 监听层从 Redis Stream 消费
3. 怎么发？      → 协议层的 SSE 格式化
```

这三件事应该分开放。端点层只管“能不能读”，监听层只管“读什么”，协议层只管“怎么发”。

### 端点层：鉴权与校验

会话级 SSE 的标准流程：

```
鉴权 → 校验 session 存在性与所有权 → 校验 Last-Event-ID
    → 返回 StreamingResponse(generator(...))
```

**要点**：

- 校验必须在创建 `StreamingResponse` 之前完成。校验失败直接抛 `HTTPException`，不建立长连接；
- `Last-Event-ID` 缺失时从 `"0"` 开始回放当前保留窗口；
- 合法格式为 `0` 或 Redis Stream ID `毫秒-序号`；非法值返回 HTTP 400；
- 会话级连接不要求某个任务处于 `processing` 状态，因为连接需要跨多个任务存活。

### 监听层：Redis Stream 消费

监听层是一个 async generator，只做一件事：从 `session_event_stream:{session_id}` 循环读取并 yield 事件。它不关心鉴权，也不关心 SSE 文本格式。

必须处理的健壮性问题：

- **Stream 尚未创建** — `XREAD` 返回空后继续等待，不做“连续空读上限”退出；连接是无限订阅；
- **Redis 连接中断** — 只对 `ConnectionError` / `TimeoutError` 做指数退避重试，重试时游标保持不变；
- **Stream 被裁剪或过期后重建** — 检测请求游标是否早于当前最早 entry；若是，先发 `: cursor-expired`，再从当前可读窗口起点继续；
- **非法或旧格式 entry** — 记 warning 后跳过，不中断连接；
- **业务事件结束** — `session.branch_task_completed`、`chat.stream_end`、`hil.stream_end` 均按普通事件下发，不结束生成器；
- **客户端断开** — generator 被取消并清理 XREAD 任务。

### 协议层：SSE 格式化

协议层只把监听层 yield 的结构化事件转成 SSE 文本，并注入控制帧。

## 统一事件信封

```json
{
  "v": 1,
  "channel": "chat",
  "type": "text_msg_delta",
  "session_id": "01945a1b-2c3d-4e5f-6789-abcdef012345",
  "session_task_id": "01945a1b-aaaa-bbbb-cccc-abcdef012345",
  "branch_name": "main",
  "payload": {
    "content": "你好"
  }
}
```

- `v` 固定为 `1`；
- `channel` 为 `session`、`chat` 或 `hil`，`system` 名称保留但 v1 无事件；
- 信封与 payload 都是 Pydantic 模型，`extra="forbid"`；
- `payload` 必须是 JSON 对象，禁止 JSON 字符串套 JSON；
- 程序内部只传 Pydantic 对象，在 Redis 边界只序列化一次，在消费端只反序列化一次；
- SSE `event` 名为 `channel.type`；
- Redis Stream entry ID 只作为 SSE `id`，不写入事件体。

## 事件帧格式

业务事件帧由 `event`、`data`、`id` 三行组成，以空行结束：

```
event:chat.text_msg_delta
data:{"v":1,"channel":"chat","type":"text_msg_delta","session_id":"01945a1b-2c3d-4e5f-6789-abcdef012345","session_task_id":"01945a1b-aaaa-bbbb-cccc-abcdef012345","branch_name":"main","payload":{"content":"你好"}}
id:1712000000000-0

```

- `event` — `channel.type`；
- `data` — 单行 JSON，项目统一使用 Pydantic 的 JSON 输出；
- `id` — Redis Stream entry ID，用于断线续读。

## 控制帧

### init

连接建立后首先发送：

```
retry:10000
event:init
data:{"status":"connected"}

```

### heartbeat

服务端空闲时每 15 秒发送一次：

```
: heartbeat

```

心跳没有 `data` 和 `id`，不派发业务事件，也不推进游标。

### cursor-expired

当 `Last-Event-ID` 早于当前 Stream 最早可读 entry 时发送：

```
: cursor-expired

```

客户端必须能区分两类注释帧。收到 `cursor-expired` 后，服务端会从当前可读窗口继续；客户端应提示可能发生历史缺口，但不能把连接视为不可恢复。

## 客户端解析约定

自定义 SSE 客户端至少需要实现：

- 按空行切分事件帧；
- 支持 `event`、`data`、`id`、`retry` 字段；
- 解析注释行，识别 `: heartbeat` 与 `: cursor-expired`；
- 仅对带 `data` 的业务事件触发业务回调；
- 维护最后收到的业务事件 ID，并在重连 POST 中通过 `Last-Event-ID` 发送；
- 不因收到 `chat.stream_end`、`hil.stream_end` 或 `session.branch_task_completed` 关闭会话级 SSE；
- 对 HIL 消息使用 `payload.msg_id` 去重；对文本增量接受 at-least-once 的重复风险。

## Redis 写入与 HIL 状态

- Chat/Session 普通事件通过 writer 的 `MULTI` pipeline 写入 `XADD` + `EXPIRE`；
- HIL 交互事件通过 Lua 原子完成 `XADD`、pending 状态写入和两个 key 的 TTL 刷新；
- HIL 状态键为 `hil_interaction_state:{session_id}`，field 为 `msg_id`，值为 `{"state":"pending|responded|acked","expires_at":<unix_ms>}`；
- `/hil/respond` 与 `/hil/ack_notification` 使用 Lua 原子转换状态并返回 404/409；
- HIL 上行响应写入 `human_in_loop_recv_stream:{session_task_id}`，格式为 JSON，不再使用 pickle。

## 错误处理的层次

| 错误类型 | 性质 | 处理方式 |
|---|---|---|
| 鉴权/资源所有权/非法游标 | 确定性错误 | 直接 HTTPException，不建连 |
| Redis 连接中断 | 临时性错误 | 指数退避重试，保持游标不变 |
| 单个 entry 解析失败 | 数据问题 | warning 日志后跳过，不中断连接 |
| 非瞬态 Redis 错误 | 确定性/未知错误 | error 日志后关闭连接，由客户端重连 |
| 客户端断开 | 正常生命周期 | 取消 generator 并清理任务 |

**原则**：校验阶段的错误用 HTTP 状态码反馈；连接建立后的运行时问题只影响当前连接，不能关闭其他信道。

## 现有实现参考

- **统一事件模型** `api/chat/session_streaming/events.py` — 信封、payload、嵌套 discriminated union、`SessionStreamEventAdapter`。
- **共享常量** `api/chat/session_streaming/constants.py` — Stream key、TTL、MAXLEN、心跳和 HIL 租约参数。
- **Writer** `api/chat/session_streaming/writer.py` — 会话 Stream 唯一写入入口、单次序列化、有限重试。
- **HIL 状态** `api/chat/session_streaming/hil_state.py` — pending 发布、租约刷新、responded/acked 原子转换。
- **Chat 生产端** `api/chat/streaming_processor.py` — 构造 Chat 事件并写入会话 Stream。
- **会话 SSE 端点** `api/app/chat/session_streaming/endpoint.py` — 鉴权、init、心跳、游标过期注释和 SSE 格式化。
- **会话 SSE 监听** `api/app/chat/session_streaming/listener.py` — 从 Redis Stream 消费、续读、HIL 状态过滤。
- **SSE 工具** `api/sse_utils.py` — 心跳帧、游标过期帧和 `iter_with_heartbeat()`。
- **HIL 上行服务** `api/human_in_loop/interaction_service.py` 与 `api/human_in_loop/http_worker/router.py` — respond/ack 和 404/409 语义。
