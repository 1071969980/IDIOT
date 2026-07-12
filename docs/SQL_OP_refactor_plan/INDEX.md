# SQL ctx 业务层候选点索引

## 状态一览

| # | 候选点 | 模块 | 优先级 | 状态 | 更新日期 |
|---|--------|------|--------|------|----------|
| 1 | [create_session 会话创建原子化](completed/create_session_session_creation.md) | chat | P0 | 已完成 | 2026-07-12 |
| 2 | [process_pending_messages 任务/消息状态联动原子化](completed/process_pending_messages_state_transition.md) | chat | P0 | 已完成 | 2026-07-12 |
| 3 | [update_tools_status 存储快照与逻辑标记原子化](completed/update_tools_status_原子化存储快照与逻辑标记.md) | chat | P1 | 已完成 | 2026-07-12 |
| 4 | [SubAgentRunner 子代理初始化原子化](completed/sub_agent_runner_transaction.md) | agent | P1 | 已完成 | 2026-07-12 |
| 5 | [scheduler update_status + update_heartbeat 原子化](archive/scheduler_update_status_heartbeat_atomic.md) | user_pod_scheduler | P2 | 已归档 | 2026-07-12 |

## 状态说明

- **待审查**：阶段一产出，等待主代理审查
- **已批准**：阶段二通过，等待用户确认
- **执行中**：阶段三进行中
- **已完成**：代码已修改并验证，文档移至 `completed/`
- **已归档**：不适合或优先级偏低，暂时搁置，文档移至 `archive/`

## 统计

- 总计：5
- 待审查：0
- 已完成：4
- 已归档：1
