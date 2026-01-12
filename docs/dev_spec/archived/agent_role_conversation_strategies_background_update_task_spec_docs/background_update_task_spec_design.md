---
文档标题：角色对话策略更新功能 - 设计文档
文档描述：描述角色对话策略更新功能的整体设计，包括整体流程、Agent循环设计、循环重试次数说明、并发安全性保证、文件操作设计和流程图。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [2.1 整体流程](#21-整体流程)
- [2.2 Agent 循环设计](#22-agent-循环设计)
- [2.3 循环重试次数说明](#23-循环重试次数说明)
- [2.4 并发安全性保证](#24-并发安全性保证)
- [2.5 文件操作设计](#25-文件操作设计)
- [流程图](#流程图)

## 2.1 整体流程

详细内容请参考：[整体流程设计](./design/01_overall_flow.md)

后台更新任务分为三个主要阶段：
- **第一阶段：计划更新任务** - 防止多个任务同时处于第一阶段等待（后来者杀死先来者）
- **第二阶段：准备文件内容** - 读取所需的用户空间文件内容到内存，并处理缓存文件
- **第三阶段：更新任务** - 执行实际的对话策略和总结指导文件更新

## 2.2 Agent 循环设计

详细内容请参考：[Agent 循环设计](./design/02_agent_loop_design.md)

第三阶段的 Agent 循环包括三个 Agent：
- **Agent A：更新对话策略文件** - 读取当前策略，根据更新请求和审查建议进行修改
- **Agent B：更新对话总结指导文件** - 根据更新后的策略修改总结指导
- **Agent C：审查更新结果** - 生成 diff，审查更新质量，给出评分和建议

## 2.3 循环重试次数说明

**工具调用重试（Agent A/B）**:
- 如果 Agent 未调用工具，立即重试
- 每个工具调用最多重试 3 次
- 超过 3 次后任务失败并回滚

**审查循环重试（Agent A → B → C 循环）**:
- 如果 Agent C 审查不通过（`score < 80`），重新执行 A → B → C
- 最多循环 3 次
- 超过 3 次后任务失败并回滚

**总执行次数上限**:
- 最坏情况下：Agent A 执行 9 次（3 次循环 × 3 次工具调用重试）
- Agent B 执行 9 次
- Agent C 执行 3 次

## 2.4 并发安全性保证

**分布式锁机制**:
- `HybridFileObject` 在 `async with` 块内自动获取分布式锁
- 锁的键名格式：`HybridFileObject:{s3_key}`
- 锁在退出 `async with` 块时自动释放

**并发读取安全性**:
- 第二阶段的文件读取操作不需要额外获取分布式锁
- 如果第三阶段正在执行（持有锁），第二阶段的读取会被阻塞
- 第三阶段完成并释放锁后，新的读取会获取最新内容
- 这种设计符合"读多写少"的场景，不需要额外的读写锁

**缓存文件并发安全**:
- 读取和清空 `strategies_update_cache.json` 在同一个 `async with` 块内执行
- `HybridFileObject` 持有分布式锁，确保原子性
- 不会发生请求丢失或竞态条件

## 2.5 文件操作设计

### 内存操作原则

**第二阶段（准备文件内容）**:
1. 一次性读取所需文件到内存：
   - `conversation_strategies.md` → `original_strategies: str`
   - `concluding_guidance.md` → `original_guidance: str`
   - `strategies_update_cache.json` → `update_cache: dict`
2. 读取后立即关闭文件句柄
3. 读取成功后，只清空 `strategies_update_cache` 数组（保留其他 JSON 结构）：
   - 提取 `strategies_list = update_cache.get("strategies_update_cache", [])`
   - 将 `update_cache["strategies_update_cache"]` 设置为 `[]`
   - 写回文件（保留其他可能的字段）
4. 如果 `strategies_list` 为空，跳过第三阶段，任务正常结束

**第三阶段（Agent 循环）**:
1. 使用内存数据构建动态工具，agent 看到的是普通的文件读写工具
2. Agent 输出结果保存到内存变量：
   - Agent A: `agent_a_result["updated_strategies"]`
   - Agent B: `agent_b_result["updated_guidance"]`
3. 审查通过后，才将内存数据写入文件系统：
   - `updated_strategies` → `conversation_strategies.md`
   - `updated_guidance` → `concluding_guidance.md`

### 缓存文件回滚机制

- 如果在第二阶段之后任何步骤失败，将读取到的 `update_cache` 写回 `strategies_update_cache.json`
- 使用 try-finally 确保回滚逻辑被执行

## 流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                        工具调用成功                              │
│                  写入缓存文件成功                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│               0. 任务启动前：发布 planning 信号                   │
│  1. 发布信号到: agent-role-update:planning:{user_id}:{role}    │
│  2. 信号作用：终止所有正在第一阶段等待的旧任务（后来者杀死先来者）│
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   第一阶段：计划更新任务                          │
│  1. 订阅分布式信号: agent-role-update:planning:{user_id}:{role} │
│  2. 等待 30 秒超时（使用 asyncio.wait_for）                      │
│  3. 如果收到信号 → 有新任务来抢占，当前任务退出                   │
│  4. 如果超时 → 没有新任务，进入第二阶段                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 第二阶段：准备文件内容                            │
│  1. 读取 conversation_strategies.md → original_strategies       │
│  2. 读取 concluding_guidance.md → original_guidance             │
│  3. 读取 strategies_update_cache.json → update_cache            │
│  4. 只清空 strategies_update_cache 数组（设为 []）               │
│  5. 如果 strategies_list 为空 → 任务结束                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   第三阶段：更新任务（Agent 循环）                │
│  1. 获取分布式锁: agent-role-update:lock:{user_id}:{role}       │
│     (如果其他任务正在执行，在锁处等待)                            │
│  2. 启动 Agent 循环：                                           │
│     - Agent A: 更新对话策略（工具调用最多重试 3 次）               │
│     - Agent B: 更新总结指导（工具调用最多重试 3 次）               │
│     - Agent C: 审查更新结果（生成 diff，评分 0-100）               │
│  3. 如果 score < 80 → 回到 Agent A（最多循环 3 次）              │
│  4. 如果 score >= 80 → 写入文件系统                              │
│  5. 释放分布式锁                                                │
└─────────────────────────────────────────────────────────────────┘
```

## 相关文档

- [整体流程设计](./design/01_overall_flow.md)
- [Agent 循环设计](./design/02_agent_loop_design.md)
- [上下文文档](./background_update_task_spec_context.md)
- [实现文档](./background_update_task_spec_implementation.md)
- [审核文档](./background_update_task_spec_review.md)
