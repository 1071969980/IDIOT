# SSE 流式接口开发规范

## 项目约定：POST + 自定义 fetch 客户端

项目中的 SSE 接口统一使用 `POST` + JSON 请求体建立连接，并通过 Bearer Token 鉴权。该方案无法使用浏览器原生 `EventSource`，因此客户端使用 `fetch` + `ReadableStream` 手动解析 SSE 帧。

这意味着以下职责由客户端自行实现：

- 解析 `event`、`data`、`id` 字段和注释行；
- 记录最后收到的业务事件 `id`；
- 在需要断线续读的接口上，重连时重新发送 POST，并手动携带 `Last-Event-ID`；
- 区分收到 `stream_end` 的正常结束和未收到 `stream_end` 的异常断开；
- 根据 `retry` 字段或应用约定决定重连间隔。

`Last-Event-ID` 仅用于基于 Redis Stream、支持续读的接口。基于 Redis Pub/Sub 的接口不读取该请求头，断线期间的事件不会补发。

## 为什么是 Redis Stream + SSE

SSE 是单向的持久 HTTP 连接，服务器可以持续推送消息。它比 WebSocket 轻量（纯 HTTP），比轮询高效（长连接）。

但 SSE 本身不解决"消息从哪来"的问题。选择 Redis Stream 作为消息管道是因为：

- **消息有序且有 ID** — 每条消息自带递增 ID，天然支持"从第 N 条开始读"
- **生产消费解耦** — 生产者写完即走，消费者随时接入，不需要同时在线
- **可持久化** — 消息不会因连接断开而丢失，客户端重连后可以续读

## 三个关注点

实现一个 SSE 接口，本质上是处理三个独立的问题：

```
1. 谁能读？      → 端点层的鉴权与校验
2. 从哪读？      → 监听层从 Redis Stream 消费
3. 怎么发？      → 协议层的 SSE 格式化
```

这三件事应该分开放。端点层只管"能不能读"，监听层只管"读什么"，协议层只管"怎么发"。

### 端点层：鉴权与校验

SSE 端点的校验逻辑和普通接口一样，但支持续读的接口还需要读取 `Last-Event-ID` 请求头。

由于客户端使用自定义 fetch 实现，`Last-Event-ID` 不会由浏览器自动携带。客户端重连时必须重新发起 POST，并手动放入最后一次收到的业务事件 ID。服务端用这个 ID 告诉 Redis Stream "从这个位置之后开始读"，从而实现断线续读。

基于 Redis Pub/Sub 的接口没有持久化游标，不应声明支持 `Last-Event-ID` 续读。

因此端点函数的标准流程是：

```
鉴权 → 校验资源存在性和所有权 → 校验任务状态
    → 取 Last-Event-ID（默认 "0"）
    → 返回 StreamingResponse(generator(...))
```

**几个要点**：

- 校验在 `StreamingResponse` 创建之前完成。如果校验失败，直接抛 HTTPException，不会建立长连接。这很重要——SSE 连接一旦建立，就没有标准的错误推送机制了。
- 需要校验任务状态是否为"进行中"。一个已结束的任务不会有新消息产生，对它建立 SSE 连接没有意义。
- 端点函数本身不关心消息内容、不关心 Redis Stream 怎么读，只做准入控制。

### 监听层：Redis Stream 消费

这一层是一个 async generator，只做一件事：从 Redis Stream 循环读取消息并 yield 出去。它不关心鉴权，不关心 SSE 协议格式。

它需要处理的是一系列**非业务的健壮性问题**：

**Stream 还没创建** — 客户端请求到达时，生产者可能尚未开始写入。这时 Redis 里还没有对应的 stream key。通过轮询等待 stream key 出现来解决，超时则放弃。这个等待是必要的，因为从"任务开始"到"生产者开始写入"之间有一个不可忽略的时间窗口。

**连接中断** — Redis 连接闪断在生产环境中很常见。捕获 `ConnectionError` 后指数退避重试（`2^n` 秒），关键是重试时 **游标（current_id）不能变**，这样连接恢复后能从断点继续读，不会丢消息也不会重复。这和端点层的 `Last-Event-ID` 是同一个思路，只不过发生在服务端内部。

**Stream 已过期** — Redis Stream 有 TTL，可能被清理。如果 stream 在读取过程中消失，XREAD 不会报错，而是阻塞到超时后返回空。通过连续空读计数来检测这种情况，超过上限则退出。这个上限应该远大于正常情况下的空读次数，它只是防止无限等待的兜底。

**正常结束** — 收到 `stream_end` 类型的消息意味着生产者已写完。yield 最后一条消息后退出 generator，上层 SSE 连接随之关闭。

### 协议层：SSE 格式化

这一层是一个薄的 async generator，负责把监听层 yield 出来的结构化数据转成 SSE 文本格式。它不关心数据从哪来，只管格式化。

协议层需要区分业务事件帧和协议控制帧。

#### 业务事件帧

```
event:事件类型
data:JSON载荷
id:消息ID

```

每条业务事件以空行结束。字段语义：

- `event` — 应用层事件类型，客户端按类型分发处理；
- `data` — 单行 JSON。项目统一使用 `ujson.dumps(..., ensure_ascii=False)`，保证中文和换行安全；
- `id` — 业务事件 ID，用于支持断线续读；客户端需要记录最后收到的业务事件 ID。

#### 协议控制帧

没有 `data` 的帧是协议控制帧，不属于业务事件，不应触发业务事件回调，也不消耗业务事件 ID。

心跳使用注释行：

```
: heartbeat

```

服务端在没有业务事件时每 15 秒发送一次心跳，避免长连接被代理或负载均衡器按空闲超时断开。

`retry` 字段用于指示重连间隔，单位是毫秒。它是标准 SSE 字段，但自定义 fetch 客户端需要自行读取并应用：

```
retry:10000

```

#### Init 帧

连接建立后先发送统一的 init 帧：

```
retry:10000
event:init
data:{"status":"connected"}

```

`retry:10000` 表示建议重连间隔为 10 秒；`event:init` 和 `data` 表示连接已就绪。

#### 正常结束

支持单次任务生命周期的接口在正常完成时应发送终止事件，然后关闭连接：

```
event:stream_end
data:{"...":"终止事件载荷"}
id:消息ID

```

客户端收到 `stream_end` 后才视为正常结束；如果连接关闭但未收到该事件，应视为异常结束并进入重连或错误处理流程。无限订阅型接口可以不发送 `stream_end`，例如会话级事件流。

## 客户端解析约定

自定义 SSE 客户端至少需要实现：

- 按空行切分事件帧；
- 忽略以 `:` 开头的注释行；
- 支持 `event`、`data`、`id`、`retry` 字段；
- 无 `data` 的帧视为协议控制帧；
- 有 `data` 无 `event` 的帧按 SSE 默认 `message` 事件处理；
- 维护最后收到的业务事件 ID，并在重连 POST 中通过 `Last-Event-ID` 发送；
- 将 `stream_end` 作为正常终止信号，将 EOF 时缺少 `stream_end` 视为异常。

## 错误处理的层次

不同类型的错误需要不同的策略：

| 错误类型 | 性质 | 处理方式 |
|---|---|---|
| 校验失败（鉴权/资源/状态） | 确定性错误 | 直接 HTTPException，不建连 |
| Redis 连接中断 | 临时性错误 | 指数退避重试，保持游标不变 |
| 连续空读超限 | 可能的任务丢失 | warning 日志 + 退出 |
| 未预期异常 | 未知错误 | error 日志 + 退出 |

**原则**：校验阶段的错误属于业务逻辑，用 HTTP 状态码反馈；连接建立后的错误属于运行时问题，用日志记录后静默结束连接。客户端通过“是否收到 `stream_end`”区分正常结束和异常断开。

如果后续需要让客户端区分具体错误类型，可以增加应用层错误事件，例如 `event:error`；在此之前不要把普通 EOF 当作正常完成。

## 可观测性

Stream 监听是一个长时间运行的异步过程，它的生命周期事件必须可追踪：

- 用 `logfire.span` 包裹整个生成器，标记开始和结束
- 正常结束用 info，可恢复问题用 warning，不可恢复问题用 error
- 日志必须包含 stream key 等上下文，方便在平台中按任务聚合排查

参考项目的日志规范：`docs/for_LLM_dev/logfire日志记录实践指南.md`

## 现有实现参考

- **统一 SSE 工具** `api/sse_utils.py` — 提供心跳控制帧 `SSE_HEARTBEAT_FRAME` 和 `iter_with_heartbeat()`，在无业务事件时触发心跳。
- **Chat 消息生产** `api/chat/streaming_processor.py` — `StreamingProcessor` 封装 Redis Stream 写入，负责状态变更、文本片段、工具调用等事件和 stream TTL。
- **Chat 消息监听** `api/chat/stream_listener.py` — `u2a_msg_stream_generator` 从 Redis Stream 消费消息，支持存在性等待、断线续读、连接重试和空读退出。
- **Chat SSE 端点** `api/app/chat/listen_to_session_streaming.py` — 完成鉴权校验后返回 `StreamingResponse`，输出 Chat 业务事件、心跳和 `stream_end`。
- **Session Event SSE 端点** `api/app/chat/session_event_streaming/` — 基于 Redis Pub/Sub 的会话级事件订阅，发送心跳控制帧，不支持断线续读。
- **HIL SSE 端点** `api/human_in_loop/http_worker/router.py` — 鉴权后输出 HIL 事件、心跳和 `stream_end`。
- **HIL 消息监听** `api/human_in_loop/http_worker/stream_listener.py` — 从 HIL Redis Stream 消费消息，并在收到 `stream_end` 时先输出终止事件再结束生成器。
