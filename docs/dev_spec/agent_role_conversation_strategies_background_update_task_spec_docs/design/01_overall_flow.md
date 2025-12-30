---
文档标题：整体流程设计
文档描述：描述后台更新任务的三个主要阶段的详细设计，包括计划更新任务、准备文件内容和更新任务的执行逻辑、返回值语义、冲突谓词和分布式信号设计。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [2.1.1 第一阶段：计划更新任务](#211-第一阶段计划更新任务)
- [2.1.2 第二阶段：准备文件内容](#212-第二阶段准备文件内容)
- [2.1.3 第三阶段：更新任务](#213-第三阶段更新任务)

## 2.1 整体流程

后台更新任务分为三个主要阶段：

### 2.1.1 第一阶段：计划更新任务 (Planning Task)

**目的**: 防止多个任务同时处于第一阶段等待（后来者杀死先来者）

**执行逻辑**:
1. **任务启动前**：立即发布 `agent-role-update:planning:{user_id}:{role_name}` 信号
   - 这个信号会终止所有**正在第一阶段等待**的旧任务
   - 实现"后来者杀死先来者"的逻辑
2. **启动第一阶段**：订阅频道，开始等待 30 秒超时
3. 如果在等待期间收到新的 planning 信号，说明有更新的任务启动，当前任务退出
4. 如果等待超时（30 秒），说明没有更新的任务启动，继续执行第二阶段

**返回值语义**:
- `True`：超时（没有新任务来抢占），继续执行第二阶段
- `False`：收到新任务的信号，当前任务退出

**冲突谓词**: 相同用户的相同角色的计划更新任务

**分布式信号设计**:
- **频道命名规则**: `agent-role-update:planning:{user_id}:{role_name}`
- **信号发布时机**: **任务启动前**（在进入第一阶段之前）
- **信号订阅时机**: 第一阶段启动时，使用 `subscribe_to_event()` 订阅频道
- **信号作用**: 终止其他正在第一阶段等待的旧任务

**超时等待实现**:
- **关键**: `subscribe_to_event()` 会阻塞直到收到消息，必须作为后台任务运行
- 使用 `asyncio.create_task()` 创建订阅任务，然后使用 `asyncio.wait_for(event.wait(), timeout=30)` 等待
- 超时后抛出 `asyncio.TimeoutError`，捕获后取消订阅任务并返回 `True`（继续执行）
- 收到信号后 `event.wait()` 返回，取消订阅任务并返回 `False`（退出任务）

**标准实现模式**:
```python
# 创建订阅任务（在后台运行）
subscribe_task = asyncio.create_task(subscribe_to_event(channel, event))

# 等待信号，超时时间为 30 秒
try:
    await asyncio.wait_for(event.wait(), timeout=PHASE1_TIMEOUT)
    # 收到信号，有新任务来抢占
    subscribe_task.cancel()
    return False
except asyncio.TimeoutError:
    # 超时，没有新任务来抢占
    subscribe_task.cancel()
    return True
finally:
    # 清理订阅任务
    try:
        await subscribe_task
    except asyncio.CancelledError:
        pass
```

**关键设计要点**:
- 第一阶段只防止"多个任务同时进入第一阶段"，不检测第三阶段状态
- 第三阶段的并发控制由**分布式锁**保证（见第三阶段说明）
- 如果新任务在旧任务的第三阶段启动，新任务会在分布式锁处等待，不会进入第三阶段

### 2.1.2 第二阶段：准备文件内容 (Prepare File Contents)

**目的**: 读取所需的用户空间文件内容到内存，并处理缓存文件

**函数签名**: `async def execute_preparation_phase(user_id: UUID, role_name: str) -> tuple[str, str, str] | None`

**执行逻辑**:
1. 读取以下文件内容到内存变量：
   - `conversation_strategies.md` → `original_strategies: str`
   - `concluding_guidance.md` → `original_guidance: str`
   - `strategies_update_cache.json` → `update_cache: dict`
2. 读取后立即关闭文件句柄
3. **缓存文件特殊处理（在同一个分布式锁内完成，确保原子性）**:
   - 使用 `r+` 模式打开缓存文件，支持同时读写
   - 在同一个 `async with` 块内完成以下操作：
     - 读取缓存文件内容并解析 `update_cache`
     - 提取更新列表：`strategies_list = update_cache.get("strategies_update_cache", [])`
     - 如果 `strategies_list` 为空数组或不存在，则跳过第三阶段，任务正常结束（返回 `None`）
     - 将 `strategies_list` 格式化为易读文本（见下方格式化逻辑）
     - 只清空 `strategies_update_cache` 数组（保留其他 JSON 结构）：将 `update_cache["strategies_update_cache"]` 设置为空数组 `[]`
     - 将清空后的 `update_cache` 写回文件（使用 `seek(0)`、`write()`、`truncate()`）
     - 关闭文件句柄并释放分布式锁
   - 如果后续任务发生异常，将读取到的原始 `update_cache` 内容写回缓存文件
   - **并发安全性**: 所有操作在同一个 `async with` 块内完成，持有分布式锁，不会发生竞态条件

**退出条件**:
- 如果 `strategies_list` 为空数组或不存在，返回 `None`，跳过第三阶段
- 如果读取文件时发生异常（文件不存在、权限错误等），记录错误日志，任务结束（返回 `None`）

**返回值**:
- 成功：返回 `(original_strategies, original_guidance, strategies_update_list)` 三个字符串的元组
  - `original_strategies`: 读取到的对话策略内容
  - `original_guidance`: 读取到的总结指导内容
  - `strategies_update_list`: 格式化后的更新请求文本
- 失败或无更新：返回 `None`

**strategies_list 格式化逻辑**:
```python
strategies_list = update_cache.get("strategies_update_cache", [])
if not strategies_list:
    return None  # 没有待处理的更新

# 格式化为易读文本
formatted_items = []
for i, item in enumerate(strategies_list, 1):
    formatted_items.append(
        f"## 更新请求 {i}\n\n"
        f"**更新内容**:\n{item['update_content']}\n\n"
        f"**相关上下文**:\n{item['context']}"
    )
strategies_update_list = "\n\n".join(formatted_items)
```

**异常处理**:
- 文件读取异常：使用 try-except 捕获，记录 logfire.error，任务结束（返回 `None`）
- 缓存文件清空异常：记录日志，但继续执行（因为已读取到内存）

### 2.1.3 第三阶段：更新任务 (Update Task)

**目的**: 执行实际的对话策略和总结指导文件更新

**函数签名**: `async def execute_update_phase(user_id: UUID, role_name: str, original_strategies: str, original_guidance: str, strategies_update_list: str) -> None`

**执行逻辑**:
1. **获取分布式锁**（阻塞等待，超时时间 300 秒）
   - 如果其他任务正在执行第三阶段，当前任务会在锁处等待
   - 锁释放后，当前任务开始执行
2. **启动 Agent 循环**，包括三个子任务：
   - 更新对话策略文件（Agent A）
   - 更新对话总结指导文件（Agent B）
   - 审查更新结果（Agent C）
3. 如果审查通过，将内存中的更新结果写入用户空间文件系统
4. 写入成功后，缓存文件已被第二阶段清空，无需额外处理
5. **释放分布式锁**
6. **无返回值**: 函数不返回任何值，成功或失败都通过日志记录

**分布式锁设计**:
- **锁命名规则**: `agent-role-update:lock:{user_id}:{role_name}`
- **锁超时时间**: 300 秒（5 分钟）
- **获取方式**: `async with RedisDistributedLock(key, timeout=300) as lock:`
- **作用**: 保证同一时间只有一个任务处于第三阶段（串行执行）

**关键设计要点**:
- **第三阶段不发布信号**：分布式锁已经保证了串行执行
- **新任务的处理**：如果在第三阶段执行期间有新任务到达，新任务会在分布式锁处等待
- **并发安全**：不会有两个任务同时修改用户空间文件

## 相关文档

- [Agent 循环设计](./02_agent_loop_design.md)
- [上下文文档](../background_update_task_spec_context.md)
- [实现文档](../background_update_task_spec_implementation.md)
