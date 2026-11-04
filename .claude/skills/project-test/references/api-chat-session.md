# 会话模块测试

会话（Session）是用户与 AI Agent 交互的核心模块。测试会话功能需要理解 Session-Task-Message 三层数据结构和一条跨任务的会话级 SSE 事件总线。

## 前置检查

确认以下三方内容一致：

1. **SKILL 文档**（本文件）中的端点、数据结构、状态流转
2. **API 文档** `docs/api/sessions.apib`、`docs/api/session_streaming.apib`、`docs/api/hil/`
3. **源代码** `api/app/chat/`、`api/chat/sql_stat/`

若发现不一致，以源代码为准，更新文档。

## 关键概念

### Session-Task-Message 三层结构

```
Session (会话)
├── Branch (分支指针，类似 git HEAD)
│   └── SessionTask (任务，树形结构)
│       ├── U2AUserMessage (用户消息, seq_index)
│       ├── U2AAgentMessage (AI 消息, sub_seq_index)
│       └── HIL 交互 (Redis Streams)
```

**Session**：用户与 Agent 的交互单元。每个用户可有多个会话。核心字段：`id`, `user_id`, `title`, `archived`。

**SessionTask**：树形结构任务节点，类似 git 的 commit。通过 `parent_task_id` 和 `tree_path`（PostgreSQL ltree）构成树。核心字段：
- `status`: `pending` → `processing` → `completed` / `failed` / `cancelled`
- `parent_task_id`: 父任务（根任务为 null）
- `tree_path`: ltree 路径
- `context_breakpoints`: 上下文断点列表
- `storage_snapshot`: 存储快照
- `logic_mark`: 逻辑标记

**Branch**：类似 git branch/HEAD，指向当前叶子 Task。所有消息接口支持 `branch_name` 参数（默认 `"main"`）。

**U2AUserMessage**（用户消息）：核心字段：
- `seq_index`: 会话内序号（递增）
- `status`: `waiting_agent_ack_user` → `agent_working_for_user` → `completed` / `error`
- `session_task_id`: 关联的任务 ID

**U2AAgentMessage**（AI 消息）：核心字段：
- `sub_seq_index`: 任务内子序号（同一任务可有多条 AI 消息）
- `status`: `streaming` → `stop` → `completed` / `error`
- `session_task_id`: 关联的任务 ID
- `json_content`: 结构化内容（可选）

### 客户端事件模型

客户端为一个会话只建立一条 SSE 连接：

```
POST /chat/session_streaming
body: {"session_id": SID}
```

该连接跨多个 `session_task_id` 持续存在，通过统一信封中的 `channel` / `type` 和 `session_task_id` 解复用：

- `session.branch_task_started/completed` → 判断任务生命周期；
- `chat.*` → 展示文本、推理、工具调用与 Chat 信道结束；
- `hil.*` → 展示人工介入请求/通知，用户通过 `/hil/respond` 或 `/hil/ack_notification` 回传；
- 任何 `stream_end` 或任务完成事件都不关闭会话级连接。

**典型交互时序**：

```
1. 为 session_id 建立 /chat/session_streaming 连接
2. send_message          → 消息入库，状态=waiting_agent_ack_user
3. process_pending_messages → 创建/激活 Task，启动 Agent，返回 session_task_id
4. SSE 推送 session.branch_task_started → 客户端得知任务开始
5. SSE 推送 chat.*           → 客户端显示 AI 回复
6. [可选] SSE 推送 hil.*     → 用户回复后 Agent 继续
7. SSE 推送 chat.stream_end + hil.stream_end + session.branch_task_completed → 任务结束，连接保持
8. 后续任务继续复用同一条连接
```

### 测试流程指导

测试一个完整的"发送消息 → Agent 回复"周期：会话级 SSE 持续监听 → 根据事件信道分类处理 → 任务结束后渲染历史供审查，连接继续接收后续任务。

**交互模式说明**：测试由 AI agent 驱动，通过离散的 `tmux send-keys` 和 `tmux capture-pane` 命令与各 SSE 脚本交互。agent 无法持续监听窗格输出，只能在每个步骤之间通过 `capture-pane` 采样当前状态，根据内容决定下一步操作。因此流程设计为"启动 → 轮询采样 → 判断 → 下一步"的离散模式。

#### 步骤 1：创建会话

```python
resp = session.post(f"{BASE_URL}/chat/sessions/create", json={"title": "测试会话"})
assert resp.status_code in (200, 201)
session_id = str(resp.json()["session_uuid"])
```

#### 步骤 2：启动事件流监听

事件流是整个流程的"信号源"，必须在 `process_pending_messages` 之前启动。脚本在 tmux 中持续运行，agent 通过 `capture-pane` 采样其输出来读取事件：

```bash
tmux new -s autotest_events -d
tmux send-keys -t autotest_events \
  "cd $SCRIPTS_DIR && uv run python sse_events.py --username user_test --session-id $SID" Enter
```

采样事件流输出（去掉 ANSI 转义码获取纯文本）：

```bash
tmux capture-pane -t autotest_events -p -S -20 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

#### 步骤 3：发送消息并触发处理

```python
# 发送消息（仅入库，不调用 LLM）
resp = session.post(f"{BASE_URL}/chat/send_message", json={
    "message": "你好",
    "session_id": session_id,
    "branch_name": "main",
})
assert resp.status_code == 200

# 触发 Agent 处理，返回 task_id
resp = session.post(f"{BASE_URL}/chat/process_pending_messages", json={
    "session_id": session_id,
    "branch_name": "main",
})
assert resp.status_code == 200
task_id = resp.json()["session_task_id"]
```

#### 步骤 4：采样同一条会话级事件流，读取 chat/HIL 事件

agent 无法实时监听，需离散地采样事件流窗格，检查是否出现 `▶ task started`：

```bash
# 采样事件流（可反复执行直到看到 task_started）
tmux capture-pane -t autotest_events -p -S -20 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

确认 `▶ task started` 出现后，不需要再建立 Chat/HIL 专用连接。当前连接会继续推送同一任务的 `chat.*` 与 `hil.*` 事件，事件信封中的 `session_task_id` 用于区分任务。测试时只启动一个 SSE 脚本即可；`sse_chat.py`、`sse_events.py`、`sse_hil.py` 只是同一会话流的不同格式化视图：

```bash
# 仅启动其中一个视图，不要同时为同一客户端建立多条逻辑订阅
tmux new -s autotest_chat -d
tmux send-keys -t autotest_chat \
  "cd $SCRIPTS_DIR && uv run python sse_events.py --username user_test --session-id $SID" Enter
```

#### 步骤 5：采样同一窗格，处理交互请求（如有）

agent 继续采样会话流窗格，检查是否出现 `✋ interrupt`：

```bash
tmux capture-pane -t autotest_chat -p -S -20 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

如果输出包含 `✋ interrupt | tool=ask_user_choice ...`，从中解析 `msg_id` 和选项，通过 API 回复：

```python
resp = session.post(f"{BASE_URL}/hil/respond", json={
    "session_task_id": task_id,
    "hil_msg_id": hil_msg_id,
    "msg": {"is_additional": False, "choice": "选项一"},
})
```

回复后 Agent 继续执行。可再次采样 chat 窗格观察后续输出：

```bash
tmux capture-pane -t autotest_chat -p -S -20 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

#### 步骤 6：采样事件流，确认任务完成

采样事件流窗格，检查是否出现 `■ task finished`：

```bash
tmux capture-pane -t autotest_events -p -S -20 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

也可用 API 确认（更可靠，不依赖采样时机）：

```python
resp = session.post(f"{BASE_URL}/chat/sessions/processing_task", json={
    "session_id": session_id,
    "branch_name": "main",
})
assert not resp.json()["has_processing_task"]  # False = 已完成
```

#### 步骤 7：渲染历史消息供审查

任务完成后，渲染完整的消息历史到文件，供用户检查对话内容是否正确：

```bash
cd $SCRIPTS_DIR && uv run python message_history.py --username user_test --session-id $SID --output /tmp/history.txt
```

#### 步骤 8：清理

```bash
# 关闭 tmux 会话
tmux kill-session -t autotest_events 2>/dev/null
tmux kill-session -t autotest_chat   2>/dev/null
tmux kill-session -t autotest_hil    2>/dev/null

# 删除测试会话（可选）
# session.post(f"{BASE_URL}/chat/delete_session", json={"session_ids": [session_id]})
```

#### 多轮对话

重复步骤 3-7 即可。同一 `branch_name="main"` 下，后续消息追加到同一条树形路径。注意 `process_pending_messages` 在有 processing 任务时返回 409，需等待前一个任务完成后再发新消息。

#### 离散交互模式要点

agent 与 tmux 的交互是**请求-响应式**的，不是事件驱动的。每次 `capture-pane` 只能看到当前窗格中可见的文本快照。因此在每个步骤中：

- **采样时机**：在 API 调用之后采样（如 `process_pending_messages` 返回后再采样事件流）
- **窗口范围**：用 `-S -20` 只看最近 20 行，避免被历史输出干扰；如需更多上下文可增大范围
- **判断逻辑**：用 `grep` 或文本匹配检查关键字符串（`task started`、`task finished`、`interrupt`）
- **重复采样**：如果没有看到期望的信号，等待几秒后再次采样，直到出现或超时

### 路由结构

FastAPI 应用的 `root_path="/api"`，chat 相关路由前缀：

```
/chat/...
  /sessions                  GET    会话列表
  /sessions/create           POST   创建/获取会话
  /sessions/processing_task  POST   查询处理中任务
  /sessions/messages_history POST   消息历史（按分支）
  /sessions/task_messages_history POST 单任务消息
  /sessions/update_title     POST   更新标题
  /send_message              POST   发送消息（不调用 LLM）
  /process_pending_messages  POST   处理未回复消息（启动 Agent）
  /session_streaming         POST   唯一会话级 SSE 事件总线
  /cancel_session_task       POST   取消任务
  /delete_session            POST   批量删除会话

/hil/...
  /respond                   POST   回复 HIL 请求
  /ack_notification          POST   确认通知已读
```

### HUMAN_IN_LOOP (HIL) 机制

Agent 执行过程中可暂停并向用户发起交互。下行事件进入会话级 Stream，上行响应写入任务级 recv_stream：

- **下行**: `session_event_stream:{session_id}`，由 `/chat/session_streaming` 推送；
- **上行**: `human_in_loop_recv_stream:{session_task_id}`，由 `/hil/respond` 原子写入；
- **状态**: `hil_interaction_state:{session_id}` 保存 `pending|responded|acked` 与租约；
- **TTL**: 1 小时自动过期。

HIL SSE 事件名：
| event 类型 | 方向 | 是否需要回复 |
|-----------|------|------------|
| `hil.HIL_interrupt_request` | Agent → 用户 | 是 |
| `hil.Notification` | Agent → 用户 | 否（ack 即可） |
| `hil.stream_end` | 系统 → 用户 | 否，仅表示当前任务 HIL 信道结束 |

已知交互类型：
- **ChoiceForm** (`ask_user_choice`): Agent 提出问题 + 选项列表，用户选择或自定义输入

### SSE 协议格式

唯一会话级 SSE 使用统一事件信封：

```
retry:10000
event:init
data:{"status":"connected"}

event:chat.text_msg_delta
data:{"v":1,"channel":"chat","type":"text_msg_delta","session_id":"...","session_task_id":"...","branch_name":"main","payload":{"content":"你好"}}
id:1712000000000-0

: heartbeat

```

- `event` 名为 `channel.type`；
- `id` 为 Redis Stream entry ID，也是 `Last-Event-ID` 游标；
- 支持 15 秒心跳注释：`: heartbeat`；
- 游标早于保留窗口时发送 `: cursor-expired`，随后从当前窗口继续；
- 任务/信道结束事件不关闭连接。

## 辅助脚本

scripts/ 目录下提供 4 个独立脚本，仅依赖 `requests`，不依赖项目代码：

| 脚本 | 用途 | 对应端点 |
|------|------|---------|
| `sse_events.py` | 格式化查看 Session 生命周期事件 | `/chat/session_streaming` |
| `sse_chat.py` | 格式化查看 Chat 事件 | `/chat/session_streaming` |
| `sse_hil.py` | 格式化查看 HIL 事件 | `/chat/session_streaming` |
| `message_history.py` | 渲染会话消息历史 | `/chat/sessions/messages_history` |

三个 SSE 脚本都连接同一条会话级事件流，只是格式化视图不同；均只需 `--session-id`。`message_history.py` 的输出格式与 `sse_chat.py` 保持一致。

所有脚本支持两种认证方式（互斥）：
- `--username USER [--password PASS]` — 自动登录获取 token（密码默认 `password_test`）
- `--token TOKEN` — 直接传入 token（跳过登录）

## 代码片段

以下片段基于 `requests.Session`，假设已通过认证模块完成登录并设置 Cookie header。

### 创建会话

```python
resp = session.post(f"{BASE_URL}/chat/sessions/create", json={"title": "测试会话"})
assert resp.status_code in (200, 201)
body = resp.json()
session_id = body["session_uuid"]
# created_new_session: True=新创建, False=返回已有空会话
```

### 发送消息

```python
resp = session.post(f"{BASE_URL}/chat/send_message", json={
    "message": "你好",
    "session_id": session_id,
    "branch_name": "main",
})
assert resp.status_code == 200
body = resp.json()
task_id = body["session_task_id"]
# message_status: "waiting_agent_ack_user"
```

**注意**：`send_message` 只是将消息入库，不触发 Agent 处理。

### 请求处理消息

```python
resp = session.post(f"{BASE_URL}/chat/process_pending_messages", json={
    "session_id": session_id,
    "branch_name": "main",
})
assert resp.status_code == 200
body = resp.json()
task_id = body["session_task_id"]
# processed_messages_id_status_map: {msg_id: "agent_working_for_user"}
```

这是触发 Agent 实际执行的端点。返回 409 表示有任务正在处理中，返回 404 表示没有待处理消息。

### 会话级 SSE 事件流（tmux + 脚本）

```bash
tmux new -s autotest_chat -d
tmux send-keys -t autotest_chat \
  "cd $SCRIPTS_DIR && uv run python sse_chat.py --username user_test --session-id $SID" Enter

# 读取输出
tmux capture-pane -t autotest_chat -p -S -30 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

### 复用同一事件流查看生命周期（tmux + 脚本）

```bash
tmux new -s autotest_events -d
tmux send-keys -t autotest_events \
  "cd $SCRIPTS_DIR && uv run python sse_events.py --username user_test --session-id $SID" Enter

# 读取输出
tmux capture-pane -t autotest_events -p -S -30 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

### 复用同一事件流查看 HIL（tmux + 脚本）

```bash
tmux new -s autotest_hil -d
tmux send-keys -t autotest_hil \
  "cd $SCRIPTS_DIR && uv run python sse_hil.py --username user_test --session-id $SID" Enter

# 读取输出
tmux capture-pane -t autotest_hil -p -S -30 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

### 回复 HIL 请求

```python
resp = session.post(f"{BASE_URL}/hil/respond", json={
    "session_task_id": task_id,
    "hil_msg_id": hil_msg_id,
    "msg": {
        "is_additional": False,
        "choice": "选项一",
    },
})
assert resp.status_code == 200
```

### 查询处理中任务

```python
resp = session.post(f"{BASE_URL}/chat/sessions/processing_task", json={
    "session_id": session_id,
    "branch_name": "main",
})
assert resp.status_code == 200
body = resp.json()
has_processing = body["has_processing_task"]
```

### 获取消息历史

```python
resp = session.post(f"{BASE_URL}/chat/sessions/messages_history", json={
    "session_id": session_id,
    "branch_name": "main",
})
assert resp.status_code == 200
messages = resp.json()["messages"]
# messages: [{"role": "user"|"assistant", "message": {...}}, ...]
```

或使用脚本渲染到文件：

```bash
cd $SCRIPTS_DIR && uv run python message_history.py --username user_test --session-id $SID --output /tmp/history.txt
```

### 取消任务

```python
resp = session.post(f"{BASE_URL}/chat/cancel_session_task", json={
    "session_id": session_id,
    "session_task_id": task_id,
})
assert resp.status_code == 200
```

### 删除会话

```python
resp = session.post(f"{BASE_URL}/chat/delete_session", json={
    "session_ids": [session_id],
})
assert resp.status_code == 200
body = resp.json()
# body["results"]: [{"session_id": ..., "success": true/false, "reason": ...}]
```

## 测试环境下的 SSE 注意事项

- K8s nginx 的 8143 端口是 HTTP，SSE 连接正常工作（SSE 不依赖 Secure cookie）
- 使用 tmux 管理 SSE 长连接，避免阻塞主测试流程
- 会话级 SSE 只需 `session_id`（在创建会话后获得）；连接可覆盖后续多个任务
- HIL 的 `session_task_id` 只用于上行 `/hil/respond` 与 `/hil/ack_notification`

### tmux 中执行脚本的环境一致性

tmux 会话的工作目录和环境变量可能与当前 shell 不同。在 tmux 中执行脚本时，必须确保：

1. **工作目录** — 切换到项目根目录（脚本路径以 `scripts/` 开头的前提）
2. **Python 环境** — 使用 `uv run` 执行，保证与项目虚拟环境一致
3. **PYTHONPATH** — 无需额外设置，`_sse_lib.py` 的导入已通过 `sys.path.insert` 处理

推荐的 tmux 命令模板：

```bash
# 脚本路径基于 skill 目录，需先 cd 到 skill 的 scripts/ 目录
SCRIPTS_DIR="<skill-path>/scripts"

# 创建 tmux 会话
tmux new -s autotest_events -d

# 用 uv run 执行，确保虚拟环境中的 requests 等依赖可用
tmux send-keys -t autotest_events \
  "cd $SCRIPTS_DIR && uv run python sse_events.py --username user_test --session-id $SID" Enter

# 读取输出
tmux capture-pane -t autotest_events -p -S -30 -J | sed -r 's/\x1B\[[0-9;]*[a-zA-Z]//g'
```

也可以将脚本复制到项目目录下执行（`uv run` 会自动使用项目的虚拟环境）。
