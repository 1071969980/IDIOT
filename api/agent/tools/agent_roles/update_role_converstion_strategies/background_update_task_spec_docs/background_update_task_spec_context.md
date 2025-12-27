# 角色对话策略更新功能 - 上下文文档

## 1.1 当前实现状态

**工具名称**: `update_conversation_strategies_of_role`

**当前功能**:
- 接收用户对其他 AI 角色对话策略的更新请求
- 参数包括：`role_name`（角色名称）、`update_content`（更新内容）、`context`（上下文）
- 将更新请求写入缓存文件 `strategies_update_cache.json`
- 返回成功消息，表示任务已提交

**关键特性**（从工具描述 `config_data_model.py:38-51` 得出）:
- 提交的内容不会直接生效
- 需要由"独立的工作流"处理，该工作流无法访问当前对话上下文
- 因此提交内容必须是"完全自包含"的
- 工具输出只表示任务提交成功，不反映实际更新结果

**当前代码位置**: `constructor.py:43-71`

## 1.2 文件系统结构

用户空间中的角色定义目录结构：

```
.agent_role_definitions/
└── {role_name}/
    ├── conversation_strategies.md      # 对话策略文件（需要被更新）
    ├── concluding_guidance.md          # 结束指导文件
    └── strategies_update_cache.json    # 更新请求缓存（当前已实现）
```

**缓存文件格式**（当前实现 `constructor.py:46-67`）:
```json
{
  "strategies_update_cache": [
    {
      "update_content": "更新内容的文本",
      "context": "相关上下文的文本"
    },
    // ... 更多更新请求
  ]
}
```

## 1.3 可用的基础设施

**Redis 分布式锁** (`<project_work_dir>/api/redis/distributed_lock.py`):
- `RedisDistributedLock` 类
- 支持自动续期的看门狗机制
- 用于防止跨进程并发访问同一资源
- 使用方式：`async with RedisDistributedLock(key, timeout=30) as lock:`

**Redis 发布订阅** (`<project_work_dir>/api/redis/pubsub.py`):
- `publish_event(channel)` - 发布事件到指定频道
- `subscribe_to_event(channel, event)` - **重要**: 此函数会阻塞直到收到消息，必须作为后台任务运行
  - 标准用法：`subscribe_task = asyncio.create_task(subscribe_to_event(channel, event))`
  - 使用后必须取消：`subscribe_task.cancel()`
- 用于跨进程的信号通知

**asyncio 后台任务**:
- 使用 `asyncio.create_task()` 创建后台任务
- 不使用 Celery（尽管项目已引入 Celery 支持）

## 1.4 技术选择约束

**明确的技术决策**:
- 使用 asyncio.Task 发布后台任务，不使用 Celery
- 任务可能跨越多个进程访问相同资源
- 使用 Redis 分布式锁 (`RedisDistributedLock`) 完成同步
- 使用 Redis pubsub (`publish_event`/`subscribe_to_event`) 完成跨进程信号通知

## 相关文件链接

- 工具构造函数: `<project_work_dir>/api/agent/tools/agent_roles/update_role_converstion_strategies/constructor.py`
- 工具配置数据模型: `<project_work_dir>/api/agent/tools/agent_roles/update_role_converstion_strategies/config_data_model.py`
- 文件系统工具函数: `<project_work_dir>/api/agent/tools/agent_roles/utils.py`
- 混合文件对象实现: `<project_work_dir>/api/user_space/file_system/fs_utils/file_object.py`
- AgentBase 类: `<project_work_dir>/api/agent/base_agent.py`
- 动态工具 DI 设计文档: `<project_work_dir>/docs/for_LLM_dev/dynamic_tool_DI的设计和使用.md`
