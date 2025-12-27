# 角色对话策略更新功能 - 审核文档

## 4. 阶段性审核清单

本文档描述了角色对话策略更新功能开发完成后应进行的审核工作。

### 4.1 功能完整性审核

- [ ] **第一阶段：计划更新任务**
  - [ ] 正确订阅 Redis 频道 `agent-role-update:planning:{user_id}:{role_name}`
  - [ ] 正确实现超时等待机制（30 秒）
  - [ ] 收到新任务的 planning 信号时，旧任务正确退出（后来者杀死先来者）
  - [ ] 超时后正确进入第二阶段

- [ ] **第二阶段：准备文件内容**
  - [ ] 正确读取三个文件到内存
  - [ ] 读取后立即关闭文件句柄
  - [ ] 正确清空缓存文件
  - [ ] 缓存为空时正确跳过第三阶段
  - [ ] 文件不存在时正确终止且不回滚

- [ ] **第三阶段：更新任务**
  - [ ] 正确获取分布式锁 `agent-role-update:lock:{user_id}:{role_name}`
  - [ ] 第三阶段不发布任何信号（分布式锁已保证串行执行）
  - [ ] Agent A、B、C 正确执行
  - [ ] 审查循环正确实现（最多 3 次）
  - [ ] 审查通过后正确写入文件系统
  - [ ] 锁超时时间设置为 300 秒

### 4.2 Agent 循环审核

- [ ] **Agent A：更新对话策略**
  - [ ] 使用 `AgentBase` 作为基类
  - [ ] 从 Langfuse 获取提示词模板 `agent-role-update/update-strategies`
  - [ ] 使用 `prompt.compile()` 编译提示词，传入业务参数
  - [ ] 构造 OpenAI 格式的记忆
  - [ ] 使用动态工具提供文件更新功能
  - [ ] 实现工具调用状态控制（使用外部容器）
  - [ ] 工具调用最多重试 3 次
  - [ ] 结果保存到内存而非文件系统

- [ ] **Agent B：更新总结指导**
  - [ ] 使用 `AgentBase` 作为基类
  - [ ] 从 Langfuse 获取提示词模板 `agent-role-update/update-guidance`
  - [ ] 使用 `prompt.compile()` 编译提示词，传入业务参数
  - [ ] 构造 OpenAI 格式的记忆
  - [ ] 使用动态工具提供文件更新功能
  - [ ] 实现工具调用状态控制（使用外部容器）
  - [ ] 工具调用最多重试 3 次
  - [ ] 结果保存到内存而非文件系统

- [ ] **Agent C：审查更新结果**
  - [ ] 使用 `AgentBase` 作为基类
  - [ ] 从 Langfuse 获取提示词模板 `agent-role-update/review-updates`
  - [ ] 使用 `prompt.compile()` 编译提示词，传入 diff 文本
  - [ ] 生成 diff（使用 Python `difflib.unified_diff`）
  - [ ] 使用动态工具提供审查结论功能（必须返回分数和建议）
  - [ ] 正确返回审查结果（`score`, `suggestions`）
  - [ ] 代码根据 `score >= 80` 判断是否通过
  - [ ] 审查不通过时正确触发重新循环（最多 3 次）

### 4.3 错误处理审核

- [ ] **异常类型区分**
  - [ ] 正确识别 `HybridFileNotFoundError`（不回滚）
  - [ ] 正确识别 `LockAcquisitionError`（不回滚）
  - [ ] 正确识别 `S3OperationError`（不回滚）
  - [ ] 正确识别 `DatabaseOperationError`（不回滚）

- [ ] **回滚机制**
  - [ ] 回滚操作用 try-except 包裹
  - [ ] 回滚失败不抛出异常
  - [ ] 回滚失败记录 logfire.warning
  - [ ] 回滚成功记录 logfire.info
  - [ ] 不掩盖原始异常信息

- [ ] **任务终止**
  - [ ] 任何异常都不向上抛出
  - [ ] 所有错误情况都记录日志
  - [ ] 确保用户空间文件不被意外修改

### 4.4 日志记录审核

- [ ] **Langfuse 元数据**
  - [ ] 正确创建 `LangFuseTraceAttributes`
  - [ ] 正确创建 `LangFuseSpanAttributes`
  - [ ] 使用 `logfire.set_baggage()` 设置上下文
  - [ ] 包含 `user_id` 和 `role_name` 元数据

- [ ] **关键日志点**
  - [ ] `task_start` - 任务开始
  - [ ] `phase1_start`, `phase1_complete` - 第一阶段
  - [ ] `phase2_start`, `phase2_complete` - 第二阶段
  - [ ] `phase3_start`, `phase3_complete` - 第三阶段
  - [ ] `files_read_success`, `files_read_failed` - 文件读取
  - [ ] `files_write_success`, `files_write_failed` - 文件写入
  - [ ] `agent_a_start`, `agent_a_complete` - Agent A
  - [ ] `agent_b_start`, `agent_b_complete` - Agent B
  - [ ] `agent_c_start`, `agent_c_complete` - Agent C
  - [ ] `review_passed`, `review_failed` - 审查结果
  - [ ] `task_complete`, `task_failed` - 任务完成
  - [ ] `cache_rollback_success`, `cache_rollback_failed` - 缓存回滚

### 4.5 命名规范审核

- [ ] **Redis 频道命名**
  - [ ] Planning 频道：`agent-role-update:planning:{user_id}:{role_name}`
  - [ ] Lock 锁：`agent-role-update:lock:{user_id}:{role_name}`

- [ ] **Langfuse 提示词路径**
  - [ ] Agent A：`agent-role-update/update-strategies`
  - [ ] Agent B：`agent-role-update/update-guidance`
  - [ ] Agent C：`agent-role-update/review-updates`
  - [ ] 使用 `prompt.compile()` 编译提示词模板
  - [ ] 传入正确的业务参数

- [ ] **日志名称**
  - [ ] 所有日志以 `agent-role-update::` 为前缀
  - [ ] 日志名称使用小写和下划线

### 4.6 文档完整性审核

- [ ] **代码注释**
  - [ ] 关键逻辑有清晰注释
  - [ ] 异常处理有说明注释
  - [ ] 文档引用链接正确

- [ ] **文档更新**
  - [ ] [上下文文档](./background_update_task_spec_context.md) 与实际代码一致
  - [ ] [设计文档](./background_update_task_spec_design.md) 与实际代码一致
  - [ ] [实现文档](./background_update_task_spec_implementation.md) 与实际代码一致
  - [ ] 文档之间的交叉引用正确

### 4.7 测试场景审核

- [ ] **正常流程**
  - [ ] 单个更新请求成功处理
  - [ ] 多个更新请求排队处理
  - [ ] 审查通过后文件正确更新

- [ ] **冲突处理**
  - [ ] 两个任务同时提交，前者（旧任务）正确退出，后者（新任务）继续执行（后来者杀死先来者）
  - [ ] 分布式锁正确工作（第三阶段串行执行）

- [ ] **异常场景**
  - [ ] 文件不存在时正确处理
  - [ ] 缓存文件为空时正确跳过
  - [ ] Agent 执行失败时正确回滚
  - [ ] 文件写入失败时正确回滚
  - [ ] 回滚失败时正确记录日志

- [ ] **边界条件**
  - [ ] 更新内容为空
  - [ ] 上下文内容为空
  - [ ] 审查分数 < 80（连续 3 次不通过）
  - [ ] 网络超时
  - [ ] 缓存文件中的 `strategies_update_cache` 数组为空
  - [ ] 工具调用连续 3 次未执行

### 4.8 性能审核

- [ ] **任务执行时间**
  - [ ] 第一阶段等待时间不超过 30 秒
  - [ ] 第三阶段锁超时时间设置为 300 秒
  - [ ] Agent 循环总执行时间在可接受范围内

- [ ] **资源使用**
  - [ ] 文件句柄正确关闭
  - [ ] 分布式锁正确释放
  - [ ] Redis 连接正确管理

### 4.9 安全性审核

- [ ] **输入验证**
  - [ ] `role_name` 参数验证
  - [ ] `update_content` 参数验证
  - [ ] `context` 参数验证

- [ ] **权限控制**
  - [ ] 用户只能访问自己的角色定义
  - [ ] 分布式锁正确隔离不同用户的资源

### 4.10 可维护性审核

- [ ] **代码结构**
  - [ ] 代码模块化清晰
  - [ ] 函数职责单一
  - [ ] 避免代码重复

- [ ] **可观测性**
  - [ ] 日志完整覆盖关键路径
  - [ ] 错误信息详细且有意义
  - [ ] Langfuse trace 完整

## 相关文档

- [上下文文档](./background_update_task_spec_context.md)
- [设计文档](./background_update_task_spec_design.md)
- [实现文档](./background_update_task_spec_implementation.md)
