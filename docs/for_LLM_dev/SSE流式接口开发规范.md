# SSE 流式接口开发规范

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

SSE 端点的校验逻辑和普通接口一样，但有**一个特殊点**：需要读取 `Last-Event-ID` 请求头。

这个头由浏览器自动附带——当 SSE 连接断开后，浏览器重连时会自动在请求中加上最后一次收到的消息 ID。服务端用这个 ID 告诉 Redis Stream "从这个位置之后开始读"，从而实现断线续读。

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

SSE 消息的格式是固定的：

```
event:事件类型\n
data:JSON载荷\n
id:消息ID\n
\n
```

每条消息以 `\n\n` 结尾。三个字段的作用各不相同：

- `event` — 让客户端可以用 `addEventListener` 按类型分别处理不同事件，而不是在一个回调里做 switch。
- `data` — 消息内容，通常是 JSON。浏览器会自动拼接多行 data 字段，所以单行 data 足够。
- `id` — 断线续读的关键。浏览器会记住最后收到的 id，重连时通过 `Last-Event-ID` 请求头发回给服务端。

连接建立后应先发一条 `init` 事件（含 `retry` 字段），告诉客户端断线后多久重连：

```
event:init\nretry:10\n\n
```

## 错误处理的层次

不同类型的错误需要不同的策略：

| 错误类型 | 性质 | 处理方式 |
|---|---|---|
| 校验失败（鉴权/资源/状态） | 确定性错误 | 直接 HTTPException，不建连 |
| Redis 连接中断 | 临时性错误 | 指数退避重试，保持游标不变 |
| 连续空读超限 | 可能的任务丢失 | warning 日志 + 退出 |
| 未预期异常 | 未知错误 | error 日志 + 退出 |

**原则**：校验阶段的错误属于业务逻辑，用 HTTP 状态码反馈；连接建立后的错误属于运行时问题，用日志记录后静默结束连接（SSE 没有标准的错误推送机制）。

## 可观测性

Stream 监听是一个长时间运行的异步过程，它的生命周期事件必须可追踪：

- 用 `logfire.span` 包裹整个生成器，标记开始和结束
- 正常结束用 info，可恢复问题用 warning，不可恢复问题用 error
- 日志必须包含 stream key 等上下文，方便在平台中按任务聚合排查

参考项目的日志规范：`docs/for_LLM_dev/logfire日志记录实践指南.md`

## 现有实现参考

项目当前的 SSE 流式聊天接口可作为上述范式的完整参考：

- **消息生产** `api/chat/streaming_processor.py` — `StreamingProcessor` 封装了 Redis Stream 写入逻辑，负责将不同阶段的事件（状态变更、文本片段、工具调用等）序列化后写入 stream，并管理 stream 的 TTL。
- **消息监听** `api/chat/stream_listener.py` — `u2a_msg_stream_generator` 是通用的 Redis Stream 消费器，处理存在性等待、断线续读、连接中断重试、空读超限退出。
- **SSE 端点** `api/app/chat/listen_to_session_streaming.py` — `chat_streaming` 完成鉴权校验后返回 `StreamingResponse`，内部调用 `_stream_generator` 将消息格式化为 SSE 协议。
- **消息类型定义** `api/chat/streaming_processor.py` 中的 `StreamingMessageType` — 定义了 `status_*`、`text_msg_*`、`reasoning_delta`、`tool_call`、`tool_response`、`stream_end` 等事件类型。
