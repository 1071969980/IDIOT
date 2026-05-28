# 调试器连接（agent-debugger）

项目在调试模式下，服务启动时会被 `debugpy.wait_for_client()` 阻塞。需要用调试器 attach 解除阻塞，服务才能正常处理请求。

agent-debugger 的角色不仅是"解除阻塞"——它同时是异常捕获工具。通过 attach 后持续监听，可以捕获服务运行时的异常事件（未捕获异常、断点命中等），在测试中发挥关键作用。

## 工具

**agent-debugger** — CLI 调试工具，支持多会话，可同时 attach 多个 debugpy 服务器。

安装后直接使用，不需要在服务端额外配置。

## 服务端的 debugpy 范式

项目的 `api/app/main.py` 在模块顶层执行：

```python
if DEBUG:
    import debugpy
    debugpy.listen(("0.0.0.0", DEBUG_PORT))
    debugpy.wait_for_client()  # 阻塞，直到调试器连接
```

这意味着：
- 服务启动后，所有 import 和初始化代码**不会执行**，直到调试器 attach
- 每个服务只有**一个 debugpy 客户端槽位**，连接失败会消耗该槽位，需要重启 Pod
- `close` 后可以**重新 attach** 同一个服务，debugpy 会继续接受新连接

## 多会话管理

agent-debugger 的 daemon 支持同时管理多个调试会话，每个 `attach` 或 `start` 创建一个独立的 session。

```bash
# 列出所有活跃会话
agent-debugger list

# 关闭整个 daemon（所有会话）
agent-debugger shutdown
```

当只有一个 session 时，命令自动作用于该 session（向后兼容）。当有多个 session 时，使用 `--session <id>` 指定目标：

```bash
agent-debugger eval "x + y" --session <session_id>
agent-debugger continue --session <session_id>
agent-debugger close --session <session_id>
```

每个 `attach` 命令会返回 `session_id`，用于后续命令定向。

## Attach 流程

### 单服务（以 api 为例）

```bash
# 1. 确认端口转发已建立
kubectl port-forward -n idiot svc/api 5678:5678 &

# 2. Attach（服务解除 wait_for_client 阻塞）
agent-debugger attach 5678
# 输出:
#   Session ID: e3e4ca88
#   Attached. Program is running.
#     Background monitoring active. Check state with 'agent-debugger status'.
```

attach 后服务立即解除阻塞并完成启动。后台事件监听自动开始，无需手动 `continue`。

```bash
# 3. 检查状态（非阻塞，随时可调用）
agent-debugger status

# 4. （可选）设置断点
agent-debugger break add "/app/api/app/chat/router.py:42"
```

### 多服务

项目中 3 个服务支持 debugpy：api、app-notification、user-pod-scheduler。可以逐个 attach，所有会话并存于同一个 daemon 中。

```bash
# 1. 先建立所有端口转发（每个服务用不同本地端口）
kubectl port-forward -n idiot svc/api 5678:5678 &
kubectl port-forward -n idiot svc/app-notification 5679:5678 &
kubectl port-forward -n idiot svc/user-pod-scheduler 5680:5678 &

# 2. 逐个 attach，每个返回独立的 session_id
agent-debugger attach 5678     # → Session ID: e3e4ca88
agent-debugger attach 5679     # → Session ID: de7f97fe
agent-debugger attach 5680     # → Session ID: c8bb5c79

# 3. 查看所有活跃会话（含子进程）
agent-debugger list

# 4. 对特定会话操作（多 session 时用 --session 定向）
agent-debugger status --session e3e4ca88
agent-debugger break add "/app/api/app/chat/router.py:42" --session e3e4ca88
```

attach 即解除阻塞。多 session 时命令需要 `--session <id>` 指定目标。用 `close --session <id>` 关闭不需要的会话。

## 常用命令

```bash
agent-debugger attach <port>                              # 连接到 debugpy
agent-debugger attach <port> --break file:line[:condition]  # attach 时设置断点
agent-debugger continue [--session <id>]                  # 恢复执行（默认非阻塞，立即返回）
agent-debugger continue --wait [--session <id>]            # 恢复执行（阻塞直到下次停止）
agent-debugger eval <expression> [--session <id>]         # 在当前帧求值表达式
agent-debugger vars [--session <id>]                      # 列出局部变量
agent-debugger stack [--session <id>]                     # 显示调用栈
agent-debugger break add <file:line[:cond]> [--session <id>]  # 添加断点（可带条件）
agent-debugger break list [--session <id>]                   # 列出所有断点
agent-debugger break rm <file:line> [--session <id>]         # 移除指定断点
agent-debugger break clear [--session <id>]                  # 清除所有断点
agent-debugger step [into|out] [--session <id>]           # 单步执行（默认非阻塞）
agent-debugger source [--session <id>]                    # 显示当前位置的源码
agent-debugger status [--session <id>]                    # 查看会话状态
agent-debugger close [--session <id>]                     # 断开指定会话（不会终止服务）
agent-debugger list                                       # 列出所有活跃会话（含子进程）
agent-debugger subprocess list [--session <id>]           # 列出会话中的子进程
agent-debugger shutdown                                   # 关闭整个 daemon
```

## 验证 attach 成功

attach 后，服务应解除 `wait_for_client()` 阻塞并完成启动。验证方式：

```bash
# 方式 1：通过 nginx 访问（需要额外 port-forward）
kubectl port-forward -n idiot svc/nginx 8143:8143 &
curl -sk https://localhost:8143/api/docs | head -c 100

# 方式 2：直接访问 api port
kubectl port-forward -n idiot svc/api 8000:8000 &
curl -s http://localhost:8000/api/docs | head -c 100
```

返回 HTML 内容（Swagger UI 页面）即说明 FastAPI 已正常启动。

## 子进程调试

### 背景：fork 死锁问题

项目中 JuiceFS worker pool 使用 `mp.Process(daemon=True)` fork 子进程。在调试模式下，主进程有 debugpy 的内部线程，fork 时子进程会继承这些线程持有的锁（futex），导致子进程死锁。表现为 worker 的 `run()` 方法中 `from juicefs import Client` 等操作永远阻塞，日志中看不到 `Worker started` 输出。

agent-debugger 通过 debugpy 的 `subProcess` 机制解决此问题：为每个 fork 的子进程自动创建独立的 debugpy adapter 连接，避免子进程依赖继承的锁。

### 子进程自动发现

attach 到服务后，debugpy 在 fork 发生时会发出 `startDebugging` 反向请求（或 `debugpyWaitingForServer` 事件作为 fallback）。agent-debugger 自动：

1. 为每个子进程建立独立的 DAP 连接和调试会话（`SubprocessSession`）
2. 将父会话的断点和异常过滤器同步到子进程
3. 父会话断点变更时自动传播到所有子进程（`onBreakpointsChanged` 回调）

### 操作子进程

使用 `<session_id>/<subprocess_id>` 路径格式定向操作子进程：

```bash
# 列出当前会话的子进程
agent-debugger subprocess list

# 查看所有会话（含子进程）
agent-debugger list
# 输出示例:
#   a1b2c3d4  state: running  (4 subprocesses)
#     a1b2c3d4/p58  state: running
#     a1b2c3d4/p64  state: running
#     a1b2c3d4/p68  state: running
#     a1b2c3d4/p70  state: running

# 对特定子进程操作
agent-debugger status --session a1b2c3d4/p58
agent-debugger eval "task_count" --session a1b2c3d4/p58
agent-debugger break add "/app/api/juiceFS/client_worker/worker.py:108" --session a1b2c3d4/p58
```

子进程会话不支持 `start`/`attach`（它们由父会话自动管理），其余命令（`vars`、`eval`、`stack`、`break`、`status`、`continue`、`step`、`source`、`close`）均可用。

### 调试 JuiceFS Worker 的典型流程

```bash
# 1. Attach 到 api 服务（即解除阻塞，后台监听自动开始）
agent-debugger attach 5678

# 2. 查看 worker pool 初始化（fork 发生后子进程自动被发现）
agent-debugger subprocess list

# 3. 在父会话设断点（自动传播到所有 worker 子进程）
agent-debugger break add "/app/api/juiceFS/client_worker/worker.py:108"

# 4. 触发 JuiceFS 操作（如注册用户），断点命中后检查变量
agent-debugger status --session <session_id>/<worker_subprocess_id>
agent-debugger vars --session <session_id>/<worker_subprocess_id>
agent-debugger stack --session <session_id>/<worker_subprocess_id>
```

## 断开连接

```bash
# 关闭特定会话
agent-debugger close --session <id>

# 关闭所有会话并停止 daemon
agent-debugger shutdown
```

close 只断开调试器连接，**不会终止服务进程**。服务会继续正常运行。

## 注意事项

- **端口转发用 `svc/` 不用 `pod/`**：Pod 重启后名称会变，Service 不变
- **连接失败会消耗 debugpy 槽位**：如果 attach 前有失败的连接尝试，debugpy 可能不再接受新连接，需要 `kubectl rollout restart` 重建 Pod
- **`close` 不会杀死服务**：可以直接断开，服务不受影响
- **`close` 后可以重新 attach**：debugpy 会继续接受新连接
- **调试模式下是单 worker (uvicorn)**：生产模式才是 4 worker (gunicorn)
- **multiprocessing fork 子进程**：项目中 JuiceFS worker pool 使用 `mp.Process(daemon=True)` fork 子进程。agent-debugger 支持子进程调试（见下方子进程调试章节），会为每个 fork 的子进程自动创建独立的调试会话
- **断点自动传播**：在父会话添加/删除/清除断点时，变更自动同步到所有子进程会话，无需手动操作

## 异常捕获

### 已验证：源码断点 + 变量检查

通过在 `refresh_token` 端点预埋 `1/0` 异常，验证了完整的断点测试流程：

1. `attach` 时通过 `--break` 设置断点：`agent-debugger attach 5678 --break "/app/api/app/auth/token.py:97"`
2. 测试脚本调用 `refresh_token` → 断点命中，服务端暂停
3. `eval "str(user.id)"` 成功获取变量值
4. `stack` 返回调用栈：`refresh_token → uvicorn`
5. 再次 `continue`（非阻塞）→ 异常触发，FastAPI 返回 500，服务不崩溃

**结论**：断点 + eval + stack 的组合可以精确定位和检查异常现场。

### 已验证：异常断点（`--catch`）

agent-debugger 支持 `--catch [filter]` 参数，在 attach 时设置异常断点。daemon 内部有后台事件循环持续监听 DAP 事件，`status` 随时反映真实状态，无需手动轮询。

Python (debugpy) 的过滤器：

| 过滤器 | 行为 | 项目实测结果 |
|--------|------|-------------|
| `uncaught`（默认） | 仅未捕获异常 | **未触发** — FastAPI 全局异常处理器捕获了异常 |
| `userUnhandled` | 异常逃逸到库/框架代码 | **触发成功，推荐** — 无 HTTPException 噪音，精确捕获用户代码异常 |
| `raised` | 所有异常（含已捕获） | **触发成功** — 但有 HTTPException 控制流噪音 |

**关键细节**：debugpy 的 filter 名是 `userUnhandled`（不是 `userUncaught`）。不认识的 filter 名会被 debugpy **静默忽略**，不会报错。VSCode 的 "User Uncaught Exceptions" 对应的是 `userUnhandled`。

**`--catch raised` 的实测效果**：
- 成功捕获目标异常（`ZeroDivisionError`），输出异常类型、消息、位置
- 但 FastAPI 使用 `HTTPException` 做控制流（401、404 等），每个请求可能触发多个噪音异常
- 需要多次 `continue`（或用 `continue --wait`）跳过噪音

**异常捕获的推荐用法**：

```bash
# 推荐：捕获逃逸到框架的异常（适合 FastAPI）
agent-debugger attach 5678 --catch userUnhandled

# 备选：捕获所有异常（有噪音）
agent-debugger attach 5678 --catch raised
```

### 后台事件循环

daemon 内部有后台事件循环持续监听 DAP 的 stopped/terminated 事件：

- **不需要手动轮询** — `status` 命令随时反映真实状态
- **异常/断点自动暂停** — 程序进入 running 后，异常或断点命中会自动将状态转为 paused
- **`continue`/`step` 默认非阻塞** — 立即返回，后台事件循环持续监听。用 `--wait` 恢复阻塞行为（等待下一个 stopped 事件）
- **非阻塞解决 per-session 队列阻塞问题** — 旧的阻塞模式下，`continue` 占住 per-session 命令队列时无法调用 `status`/`eval` 等命令。非阻塞模式下 `continue` 立即返回，队列不被占住

典型工作流：
```bash
agent-debugger attach 5678 --catch userUnhandled
# attach 即解除阻塞，后台持续监听异常
# ... 运行测试脚本触发异常 ...
agent-debugger status    # 非阻塞查看当前状态（paused? running?）
agent-debugger eval "str(user.id)"  # 检查变量
agent-debugger stack     # 查看调用栈
agent-debugger continue  # 恢复执行（默认非阻塞，立即返回）
agent-debugger status    # 随时检查是否再次暂停
```

### 断点测试的注意事项

- **attach 时设置断点**：`--break` 和 `--catch` 在 attach 时指定；运行时通过 `break add` / `break rm` / `break clear` 管理
- **断点列表**：`break list` 查看当前所有断点
- **容器内路径**：断点路径必须用容器内绝对路径（`/app/api/...`），不是宿主机路径
- **断点行号**：需对齐容器内代码的实际行号（与构建时的源码一致）
- **filter 名精确匹配**：debugpy 静默忽略未知的 filter 名，不会报错。Python 可用：`uncaught`、`userUnhandled`、`raised`

### 待验证的功能

| 功能 | 说明 | 状态 |
|------|------|------|
| `--catch userUnhandled` | FastAPI 项目推荐过滤器 | **已验证** — 精确捕获用户代码异常，无 HTTPException 噪音 |
| 子进程调试 | `subprocess list` + `<session>/<subprocess>` 定向操作 fork 子进程 | **已验证** — API 的 4 个 JuiceFS worker 全部自动发现，Worker started 日志确认无死锁 |
| 断点自动传播 | 父会话断点变更自动同步到子进程 | **已验证** — `onBreakpointsChanged` 回调机制 |
| 条件断点 | `--break "file:line:condition"` / `break add "file:line:condition"` — 满足条件时暂停 | 待验证 |
| 断点管理 | `break list` / `break rm` / `break clear` — 运行时 CRUD | **已验证** — 子命令模式，支持条件断点 |
| 子进程异常捕获 | fork 的 worker 进程中的异常能否被子进程会话捕获 | 待验证 |
| 多会话异常监听 | 同时监听多个服务的异常事件 | 待验证 |
| source 命令 | 查看断点处源码（需容器内文件路径） | 报错 File not found，待排查 |

## 替代方案

除了 agent-debugger，还有以下方式连接 debugpy：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **agent-debugger** | CLI 原生，多会话，断点/eval/stack 全功能 | — |
| **VS Code Remote Debug** | GUI 友好，多服务同时 attach | 需要手动操作，不适合自动化 |
